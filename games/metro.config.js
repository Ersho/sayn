const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);

// three's CommonJS build (what react-three-fiber requires) calls process.emitWarning, which Hermes lacks;
// always use the ES module build instead.
const threeModule = path.join(__dirname, "node_modules", "three", "build", "three.module.js");
const resolve = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) =>
  moduleName === "three"
    ? { type: "sourceFile", filePath: threeModule }
    : (resolve ?? context.resolveRequest)(context, moduleName, platform);

module.exports = config;
