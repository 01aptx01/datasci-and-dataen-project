import { startStitch } from "./stitch.js";

const root = document.getElementById("root");
if (!(root instanceof HTMLElement)) throw new Error("Missing #root application element");
startStitch(root);
