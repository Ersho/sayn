// R8 strips the GLView constructor that Expo creates by reflection, so the release build crashes on the first canvas.
const { withDangerousMod } = require("expo/config-plugins");
const fs = require("fs");
const path = require("path");

const RULE = "-keep class expo.modules.gl.** { *; }";

module.exports = (config) =>
  withDangerousMod(config, [
    "android",
    (cfg) => {
      const file = path.join(cfg.modRequest.platformProjectRoot, "app", "proguard-rules.pro");
      const text = fs.readFileSync(file, "utf8");
      if (!text.includes(RULE)) fs.writeFileSync(file, `${text.trimEnd()}\n\n# expo-gl\n${RULE}\n`);
      return cfg;
    },
  ]);
