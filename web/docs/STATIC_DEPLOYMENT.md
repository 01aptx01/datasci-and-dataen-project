# Static deployment guide

This guide prepares the verified dashboard bundle for a static host. It does not publish or deploy the site.

## Build

From the repository root:

```powershell
cd web
npm install
npm run build
npm test
```

The publishable bundle is `web/dist`. The build validates the pinned handoff ZIP, member hashes, source IDs, row schemas, and the runtime allowlist before copying public snapshot files.

## Publish beneath a path

Copy the **contents** of `web/dist` to the directory served by the static host. Keep this layout together:

```text
index.html
styles.css
snapshot.policy.json
assets/
snapshots/<evaluation-id>/
```

Serve the directory URL with a trailing slash and configure `index.html` as its default document. For a project site such as `https://host.example/group/dashboard/`, the browser resolves scripts, styles, policy, and snapshot CSVs relative to that directory. Dashboard routes use URL fragments (`#/overview`, `#/models`, and so on), so reloading a route requests the same `index.html` entry point.

Do not publish the handoff ZIP, `public/snapshots`, Python source, reports, notebooks, checkpoints, or any file outside `web/dist`. The adapter copies only the approved CSV subset and generated dashboard manifest.

## Verify the hosted bundle

Before sharing the site, open its directory URL and check that:

- the snapshot banner reports successful verification and shows the pinned Evaluation and Replay ID prefixes;
- all eight hash routes load and survive a reload;
- Overview and Provenance show the frozen replay mode, strict cutoff, and pending report approval;
- the browser console has no dashboard errors;
- source requests resolve under the nested directory, with no requests to a repository root path.

The bundled app is read-only apart from the local portfolio covariance what-if and user-requested forecast exports. There is no live data endpoint or server-side ML execution.
