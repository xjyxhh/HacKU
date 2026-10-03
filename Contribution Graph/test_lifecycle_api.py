import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

from contribution_store import ContributionStore
from dashboard_server import create_app
from test_auth_support import AuthenticatedClient
from token_store import TokenStore
from export_json import export_json
from import_json import import_json
from migrate_token_ledger import migrate_project
from backup_restore import backup_and_rehearse


class LifecycleApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.db=self.root/"data.sqlite3"
        store=ContributionStore(self.db)
        store.create_project("p","Project")
        for member in ("alice","bob"):
            store.add_member("p",member,member.title())
        store.add_task("p","task","Task",10)
        store.submit_contribution("p","c","alice","task","CORE","Work")
        store.review_contribution("c","bob","CONFIRM")
        self.app=create_app(self.db,self.root/"token.sqlite3")
        self.client=AuthenticatedClient(self.app)
        self.addCleanup(self.client.close)
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT OR IGNORE INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)",("alice",b"test-auth-fixture",hashlib.scrypt(self.client.password.encode(),salt=b"test-auth-fixture",n=2**14,r=8,p=1,dklen=32)))
            conn.execute("INSERT OR IGNORE INTO auth_accounts(member_id,salt,password_hash,is_site_admin) VALUES(?,?,?,1)",("bob",b"test-auth-fixture",hashlib.scrypt(self.client.password.encode(),salt=b"test-auth-fixture",n=2**14,r=8,p=1,dklen=32)))

    def test_project_creation_makes_admin_and_separate_hashed_ledger(self):
        created=self.client.post("/api/projects",json={"id":"new-project","name":"New project"})
        self.assertEqual(created.status_code,201,created.text)
        self.assertEqual(created.json()["tokenLedgerState"],"READY")
        with sqlite3.connect(self.db) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM project_members WHERE project_id='new-project' AND member_id='_test_admin'").fetchone())
            self.assertIsNone(conn.execute("SELECT 1 FROM auth_project_admins WHERE project_id='new-project' AND member_id='_test_admin'").fetchone())
        path=self.root/"token-ledgers"/(hashlib.sha256(b"new-project").hexdigest()+".sqlite3")
        self.assertTrue(path.is_file())
        status=self.client.get("/api/projects/new-project/token/status")
        self.assertEqual(status.json()["state"],"READY")
        self.assertEqual(TokenStore(path).project.treasury_id,"new-project-treasury")
        second=self.client.post("/api/projects",json={"id":"second","name":"Second"})
        self.assertEqual(second.status_code,201,second.text)
        other=self.root/"token-ledgers"/(hashlib.sha256(b"second").hexdigest()+".sqlite3")
        self.assertTrue(other.is_file())
        self.assertNotEqual(TokenStore(path).project.id,TokenStore(other).project.id)

    def test_withdrawal_approval_sets_effective_score_zero_and_preserves_history(self):
        self.client._login("alice")
        requested=self.client.post("/api/contributions/c/unwind-requests",json={"reason":"Duplicate entry"})
        self.assertEqual(requested.status_code,201,requested.text)
        self.assertEqual(self.client.get("/api/projects/p/dashboard").json()["contributions"][0]["score"],10)
        self.client._login("bob")
        decision=self.client.post(f"/api/contributions/c/unwind-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE","note":"Agreed"})
        self.assertEqual(decision.status_code,200,decision.text)
        data=self.client.get("/api/projects/p/dashboard").json()
        self.assertEqual(data["contributions"][0]["withdrawalState"],"WITHDRAWN")
        self.assertEqual(data["contributions"][0]["score"],0)
        detail=self.client.get("/api/contributions/c").json()
        self.assertEqual(detail["contribution"]["status"],"VERIFIED")

    def test_member_exit_records_snapshot_and_preserves_global_membership(self):
        self.client._login("alice")
        requested=self.client.post("/api/projects/p/members/me/exit-requests",json={"reason":"Leaving project"})
        self.assertEqual(requested.status_code,201,requested.text)
        self.client._login("bob")
        decision=self.client.post(f"/api/projects/p/members/alice/exit-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE"})
        self.assertEqual(decision.status_code,200,decision.text)
        self.assertTrue(decision.json()["accountRetained"])
        with sqlite3.connect(self.db) as conn:
            state=conn.execute("SELECT state FROM project_membership_state WHERE project_id='p' AND member_id='alice'").fetchone()[0]
            member=conn.execute("SELECT 1 FROM members WHERE id='alice'").fetchone()
            withdrawn=conn.execute("SELECT 1 FROM contribution_withdrawals WHERE contribution_id='c'").fetchone()
        self.assertEqual(state,"WITHDRAWN")
        self.assertIsNotNone(member)
        self.assertIsNotNone(withdrawn)

    def test_exit_preview_lists_sole_admin_and_approval_blocks_until_transfer(self):
        self.client._login("bob")
        self.client._login("alice")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM auth_project_admins WHERE project_id='p' AND member_id='bob'")
        preview=self.client.get("/api/projects/p/members/me/exit-preview")
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertTrue(any("唯一项目管理员" in item for item in preview.json()["blockers"]))
        requested=self.client.post("/api/projects/p/members/me/exit-requests",json={"reason":"Leaving later"})
        self.assertEqual(requested.status_code,201,requested.text)
        self.client._login("bob")
        with sqlite3.connect(self.db) as conn:
            conn.execute("DELETE FROM auth_project_admins WHERE project_id='p' AND member_id='bob'")
        decided=self.client.post(f"/api/projects/p/members/alice/exit-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE"})
        self.assertEqual(decided.status_code,409,decided.text)

    def test_frozen_token_blocks_exit_approval(self):
        self.assertEqual(self.client.post("/api/projects/p/token/setup/retry",json={}).status_code,200)
        frozen=self.client.post("/api/projects/p/token/freeze",json={"sequences":[1],"reason":"Investigation"})
        self.assertEqual(frozen.status_code,200,frozen.text)
        self.client._login("alice")
        preview=self.client.get("/api/projects/p/members/me/exit-preview").json()
        self.assertEqual(preview["frozen"],"10")
        requested=self.client.post("/api/projects/p/members/me/exit-requests",json={"reason":"Leaving after resolution"})
        self.assertEqual(requested.status_code,201,requested.text)
        self.client._login("bob")
        decided=self.client.post(f"/api/projects/p/members/alice/exit-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE"})
        self.assertEqual(decided.status_code,409,decided.text)

    def test_archive_is_recoverable_and_stale_preview_is_rejected(self):
        preview=self.client.get("/api/projects/p/archive-preview").json()
        archived=self.client.post("/api/projects/p/archive",json={"project_id":"p","version":preview["version"],"reason":"Completed"})
        self.assertEqual(archived.status_code,200,archived.text)
        repeated=self.client.post("/api/projects/p/archive",json={"project_id":"p","version":preview["version"],"reason":"Completed"})
        self.assertEqual(repeated.status_code,200,repeated.text)
        self.assertTrue(repeated.json()["idempotent"])
        self.assertEqual(self.client.get("/api/projects/p/dashboard").status_code,410)
        self.assertNotIn("p",[project["id"] for project in self.client.get("/api/projects").json()])
        spoofed=self.client.post("/api/contributions/c/unwind-requests",json={"reason":"After archive","project_id":"other"})
        self.assertEqual(spoofed.status_code,410,spoofed.text)
        restored=self.client.post("/api/projects/p/restore",json={"reason":"Reopened"})
        self.assertEqual(restored.status_code,200,restored.text)
        self.assertTrue(self.client.post("/api/projects/p/restore",json={"reason":"Reopened"}).json()["idempotent"])
        self.assertEqual(self.client.get("/api/projects/p/dashboard").status_code,200)

    def test_partial_transfer_withdrawal_records_debt_and_retry_is_idempotent(self):
        setup=self.client.post("/api/projects/p/token/setup/retry",json={})
        self.assertEqual(setup.status_code,200,setup.text)
        self.client._login("alice")
        transferred=self.client.post("/api/projects/p/token/transfer",json={"event_id":"sent","source_id":"alice","destination_id":"bob","amount":"4","task_id":"task","evidence_hashes":["transfer:sent"]})
        self.assertEqual(transferred.status_code,200,transferred.text)
        requested=self.client.post("/api/contributions/c/unwind-requests",json={"reason":"Withdraw value"})
        self.client._login("bob")
        approved=self.client.post(f"/api/contributions/c/unwind-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE"})
        self.assertEqual(approved.status_code,200,approved.text)
        ledger=self.client.get("/api/projects/p/token/ledger").json()
        self.assertEqual(ledger["balancesExact"]["alice"],"0")
        self.assertEqual(ledger["balancesExact"]["bob"],"4")
        debts=self.client.get("/api/projects/p/token/debts").json()
        self.assertEqual(debts[0]["id"],"withdraw:c")
        self.assertEqual(debts[0]["remainingExact"],"4")
        before=len(ledger["events"])
        retried=self.client.post("/api/projects/p/unwind-outbox/reconcile",json={})
        self.assertEqual(retried.status_code,200,retried.text)
        self.assertEqual(len(self.client.get("/api/projects/p/token/ledger").json()["events"]),before)
        preview=self.client.get("/api/projects/p/archive-preview").json()
        self.assertEqual(preview["tokenLedger"]["debts"][0]["remainingExact"],"4")
        archived=self.client.post("/api/projects/p/archive",json={"project_id":"p","version":preview["version"],"reason":"Accounting closed"})
        self.assertEqual(archived.status_code,200,archived.text)
        detail=self.client.get("/api/admin/projects/p").json()
        self.assertEqual(detail["archiveSnapshots"][-1]["payload"]["tokenLedger"]["debts"][0]["remainingExact"],"4")

    def test_multi_project_snapshot_keeps_both_ledgers(self):
        self.assertEqual(self.client.post("/api/projects/p/token/setup/retry",json={}).status_code,200)
        created=self.client.post("/api/projects",json={"id":"new","name":"New"})
        self.assertEqual(created.status_code,201,created.text)
        snapshot=self.root/"snapshot.json"
        export_json(self.db,snapshot,self.root/"token.sqlite3")
        import json
        data=json.loads(snapshot.read_text())
        self.assertEqual(set(data["token_ledgers"]),{"p","new"})
        restored_root=self.root/"restored"
        restored_root.mkdir()
        import_json(snapshot,restored_root/"data.sqlite3")
        for project_id in ("p","new"):
            path=restored_root/"token-ledgers"/(hashlib.sha256(project_id.encode()).hexdigest()+".sqlite3")
            self.assertEqual(TokenStore(path).project.id,project_id)

    def test_exit_unwinds_contribution_then_sweeps_remaining_balance(self):
        self.assertEqual(self.client.post("/api/projects/p/token/setup/retry",json={}).status_code,200)
        cap=self.client.post("/api/projects/p/token/tasks/task/cap",json={"mint_cap":"20"})
        self.assertEqual(cap.status_code,200,cap.text)
        extra=self.client.post("/api/projects/p/token/mint",json={"event_id":"extra","task_id":"task","recipient_id":"alice","amount":"3","evidence_hashes":["extra:proof"]})
        self.assertEqual(extra.status_code,200,extra.text)
        self.client._login("alice")
        requested=self.client.post("/api/projects/p/members/me/exit-requests",json={"reason":"Moving on"})
        self.assertEqual(requested.status_code,201,requested.text)
        self.client._login("bob")
        approved=self.client.post(f"/api/projects/p/members/alice/exit-requests/{requested.json()['id']}/decision",json={"decision":"APPROVE"})
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertEqual(approved.json()["accountingState"],"COMPLETE")
        ledger=self.client.get("/api/projects/p/token/ledger").json()
        self.assertEqual(ledger["balancesExact"]["alice"],"0")
        self.assertTrue(any(event["id"]=="member:p:alice:exit-sweep:treasury" and event["amountExact"]=="3" for event in ledger["events"]))
        self.client._login("alice")
        denied=self.client.post("/api/projects/p/contributions",json={"id":"late","contributor_id":"alice","task_id":"task","type":"CORE","description":"Late"})
        self.assertEqual(denied.status_code,403)

    def test_legacy_alias_stays_on_migrated_original_project(self):
        migrate_project(self.db,self.root/"token.sqlite3","p")
        self.assertEqual(self.client.get("/api/projects/p/token/status").json()["state"],"READY")
        old_count=len(TokenStore(self.root/"token.sqlite3").ledger.events)
        self.assertEqual(self.client.post("/api/projects/p/token/tasks/task/cap",json={"mint_cap":"20"}).status_code,200)
        minted=self.client.post("/api/projects/p/token/mint",json={"event_id":"scoped-extra","task_id":"task","recipient_id":"alice","amount":"2","evidence_hashes":["scoped:proof"]})
        self.assertEqual(minted.status_code,200,minted.text)
        self.assertEqual(len(TokenStore(self.root/"token.sqlite3").ledger.events),old_count)
        self.assertTrue(any(event["id"]=="scoped-extra" for event in self.client.get("/api/token/ledger").json()["events"]))
        self.assertEqual(self.client.post("/api/projects",json={"id":"other","name":"Other"}).status_code,201)
        self.assertEqual(self.client.get("/api/projects/other/token/ledger").json()["events"],[])
        self.client._login("bob")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE auth_accounts SET is_site_admin=0 WHERE member_id='bob'")
            conn.execute("DELETE FROM auth_project_admins WHERE project_id='p' AND member_id='bob'")
            conn.execute("INSERT OR IGNORE INTO project_members(project_id,member_id) VALUES('other','bob')")
            conn.execute("INSERT OR IGNORE INTO project_membership_state(project_id,member_id) VALUES('other','bob')")
            conn.execute("INSERT OR IGNORE INTO auth_project_admins(project_id,member_id) VALUES('other','bob')")
        blocked=self.client.post("/api/token/transfer",json={"event_id":"wrong-alias","source_id":"alice","destination_id":"bob","amount":"1","task_id":"task","evidence_hashes":["wrong:alias"],"project_id":"other"})
        self.assertEqual(blocked.status_code,403,blocked.text)
        self.assertEqual(self.client.get("/api/projects/p/token/debts").status_code,200)

    def test_backup_restore_rehearsal_reads_dashboard_and_ledger(self):
        self.assertEqual(self.client.post("/api/projects/p/token/setup/retry",json={}).status_code,200)
        result=backup_and_rehearse(self.db,self.root/"backup")
        self.assertEqual(result["projects"],["p"])
        self.assertEqual(result["tokenLedgers"]["p"]["events"],1)
        restored=ContributionStore(self.root/"backup/restore-rehearsal/data.sqlite3")
        self.assertEqual(restored.dashboard_data("p")["contributions"][0]["score"],10)

    def test_archive_and_token_write_cannot_both_commit_after_same_preview(self):
        self.assertEqual(self.client.post("/api/projects/p/token/setup/retry",json={}).status_code,200)
        preview=self.client.get("/api/projects/p/archive-preview").json()
        other=AuthenticatedClient(self.app)
        self.addCleanup(other.close)
        start=Barrier(2)
        def archive():
            start.wait()
            return other.post("/api/projects/p/archive",json={"project_id":"p","version":preview["version"],"reason":"Concurrent close"})
        def transfer():
            start.wait()
            return self.client.post("/api/projects/p/token/transfer",json={"event_id":"race-transfer","source_id":"alice","destination_id":"bob","amount":"1","task_id":"task","evidence_hashes":["race:proof"]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            archive_result=pool.submit(archive)
            transfer_result=pool.submit(transfer)
            states=(archive_result.result().status_code,transfer_result.result().status_code)
        self.assertIn(states,((200,410),(409,200)),states)


if __name__=="__main__": unittest.main()
