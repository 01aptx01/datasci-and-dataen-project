import { startApp } from "./app.js";

const root = document.getElementById("root");
if (!(root instanceof HTMLElement)) throw new Error("Missing #root application element");
startApp(root);
