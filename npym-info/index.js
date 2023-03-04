const path = require("path");
const fs = require("fs");

/**
 * This function checks if we're currently in a package installed by NPyM. This
 * can be done by looking if within the parents folders of this file there is a
 * npym folder, and then if at the same level there is a /^npym-.*\.dist-info$/
 * folder.
 */
function inNpym() {
    const npymDistInfoRegex = /^npym-.*\.dist-info$/;
    const currentDir = path.dirname(__filename);
    const currentDirParts = currentDir.split(path.sep);
    const npymDirIndex = currentDirParts.indexOf("npym");

    if (npymDirIndex === -1) {
        return false;
    }

    const npymParentDir = currentDirParts.slice(0, npymDirIndex).join(path.sep);

    for (const brotherDir of fs.readdirSync(npymParentDir)) {
        if (npymDistInfoRegex.test(brotherDir)) {
            return true;
        }
    }

    return false;
}

module.exports = {
    inNpym,
};
