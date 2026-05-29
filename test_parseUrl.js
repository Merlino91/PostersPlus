const fs = require('fs');
const html = fs.readFileSync('configurator.html', 'utf8');

// The error might be in how parseUrl logic maps params to ui elements
const match = html.match(/function parseUrl[^}]*}/);
if (match) {
  console.log("Found parseUrl");
} else {
  console.log("Could not find parseUrl directly");
}
