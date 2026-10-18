// Makes the Android release build sign with the vibeApping keystore.
// Reads VIBE_KEYSTORE, VIBE_ALIAS, VIBE_PASSWORD from android/gradle.properties,
// which the backend writes before every build.
const { withAppBuildGradle } = require("expo/config-plugins");

const RELEASE_CONFIG = `
        release {
            storeFile file(VIBE_KEYSTORE)
            storePassword VIBE_PASSWORD
            keyAlias VIBE_ALIAS
            keyPassword VIBE_PASSWORD
        }`;

module.exports = function withVibeSigning(config) {
  return withAppBuildGradle(config, (mod) => {
    let gradle = mod.modResults.contents;
    if (!gradle.includes("VIBE_KEYSTORE")) {
      gradle = gradle.replace(/signingConfigs\s*\{/, (m) => m + RELEASE_CONFIG);
      // The release build type ships pointing at the debug signing config; repoint it.
      gradle = gradle.replace(
        /(release\s*\{[^}]*?)signingConfig signingConfigs\.debug/,
        "$1signingConfig signingConfigs.release"
      );
      if (!gradle.includes("signingConfigs.release")) {
        throw new Error("withVibeSigning: could not patch release signingConfig in app/build.gradle");
      }
    }
    mod.modResults.contents = gradle;
    return mod;
  });
};
