// Minimum supported Node versions from the pinned Expo 58 / React Native 0.88 template.
const [major, minor] = process.versions.node.split('.').map(Number);
if (!((major === 22 && minor >= 13) || (major === 24 && minor >= 3) || major >= 26)) {
  console.error(`Node 22.13+, 24.3+, or 26+ is required (found ${process.version}). Install a supported Node LTS release from https://nodejs.org.`);
  process.exit(1);
}
