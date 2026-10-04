// The interface uses English; user-supplied project data is rendered unchanged.
const I18n = Object.freeze({language: "en", t: (value) => value, register() {}, apply() {}});
document.documentElement.lang = "en";
