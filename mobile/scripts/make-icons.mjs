import sharp from "sharp";
import { writeFileSync } from "node:fs";

const BRAND = "#1d4ed8", DARK = "#1e3a8a", LIGHT = "#93c5fd";

// Three rounded bars with leading dots — a worklist. Geometry only, no fonts, so
// it renders identically wherever the assets are regenerated.
const mark = (scale = 1, opacity = 1) => {
  const rows = [
    { y: 300, w: 380, c: "#ffffff" },
    { y: 462, w: 300, c: LIGHT },
    { y: 624, w: 220, c: "#ffffff" },
  ];
  const bars = rows
    .map(
      (r) =>
        `<circle cx="300" cy="${r.y + 36}" r="36" fill="${r.c}"/>` +
        `<rect x="380" y="${r.y}" width="${r.w}" height="72" rx="36" fill="${r.c}"/>`
    )
    .join("");
  return `<g opacity="${opacity}" transform="translate(512 512) scale(${scale}) translate(-512 -512)">${bars}</g>`;
};

const gradient = `
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${BRAND}"/>
      <stop offset="100%" stop-color="${DARK}"/>
    </linearGradient>
  </defs>`;

const svg = (body, size = 1024) =>
  Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 1024 1024">${body}</svg>`);

const out = (name, buf) =>
  sharp(buf).png().toFile(`resources/${name}`).then(() => console.log("wrote resources/" + name));

await out("icon.png", svg(`${gradient}<rect width="1024" height="1024" fill="url(#g)"/>${mark(0.78)}`));
// Android adaptive icons: the foreground is masked to a safe zone, so the mark is
// smaller and the background is a flat plate.
await out("icon-foreground.png", svg(`<rect width="1024" height="1024" fill="none"/>${mark(0.52)}`));
await out("icon-background.png", svg(`${gradient}<rect width="1024" height="1024" fill="url(#g)"/>`));

const splashBody = (bg) =>
  `${gradient}<rect width="1024" height="1024" fill="${bg}"/>${mark(0.42, 0.95)}`;
await sharp(svg(splashBody("url(#g)")))
  .resize(2732, 2732, { fit: "contain", background: DARK })
  .png().toFile("resources/splash.png").then(() => console.log("wrote resources/splash.png"));
await sharp(svg(splashBody(DARK)))
  .resize(2732, 2732, { fit: "contain", background: "#0b1220" })
  .png().toFile("resources/splash-dark.png").then(() => console.log("wrote resources/splash-dark.png"));
