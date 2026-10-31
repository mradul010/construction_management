# Qatra List View Asset Deployment

## Investigation: 2026-10-31

Target: `https://qatra.k.frappe.cloud`. Owning app: `construction_management`.
Local comparison site: `Qatra.local`, not the production bench/site identity.

The width-only source fix is already committed at
`0c43246f1fad4e2a480227fa0d1e66df1e7e2829` (27-thu-004). It removed the old
header replacement/reordering implementation, retained native List View rendering,
and preserved `List.enhanced_list_view` per-user/per-DocType settings. Existing
legacy `columns` widths remain readable; the `widths` map takes precedence. No
user settings were reset by this change.

Repository: `https://github.com/mradul010/construction_management.git`.
Local branch and freshly checked remote `test-pankaj`:
`2c8808b26012b37aabab749071fb9db8dc06e7fa`.
Remote `version-16` at inspection:
`f971242f12b1cf15e22b1a520f1840c3167f9d90`.
Neither value establishes which revision/branch the Cloud site is running.

Anonymous production HTTP inspection found both original public assets already
byte-identical to the fixed local implementation:

| Asset | SHA-256 |
| --- | --- |
| JS `public/js/enhanced_list_view/enhanced_list_view.js` | `681ae0ff6ca4fceec00eb2cbf3bb5a68c16fe6e5c35b264e6a9b219df678c958` |
| CSS `public/css/enhanced_list_view/enhanced_list_view.css` | `4b8e6e8b2e589671e01d6341466d977b10677ba38a524cd392e69bca3f36d7e0` |

The JS response has `Cache-Control: max-age=31536000, immutable`, despite the hook
using a fixed, unversioned URL. This is a confirmed cache-invalidation defect and
a strong explanation for a browser continuing to execute the old Drag/reordering
code. It is not proof of the affected user's browser cache contents. A competing
production Client Script cannot be ruled out without authenticated access.

Local installed apps are Frappe, ERPNext, HRMS, Print Designer,
construction_management and qatra_custom. Searches found one active List View
implementation and one JS/CSS hook pair in construction_management, no competing
qatra_custom inclusion, and no matching local Client Scripts. Unrelated vendor
libraries and other sites' custom apps are not loaded in Qatra's hooks.
Installed Frappe ListView has automatic width calculation but no equivalent
interactive resize handles to substitute for the existing width-only behavior.

## Prepared Correction

`hooks.py` now references `construction_list_view.bundle.js` and
`construction_list_view.bundle.css` instead of the two raw asset URLs.
The JS entry imports the existing implementation exactly once; the SCSS entry
loads the existing CSS. Frappe's native asset manifest supplies content-hashed
URLs. There is no second ListView patch, new DOM observer, CSS badge hiding,
reordering handler, typography override, or change to width persistence.

Files to include in this deployment change only:

- `construction_management/hooks.py`
- `construction_management/public/js/construction_list_view.bundle.js`
- `construction_management/public/css/construction_list_view.bundle.scss`
- `construction_management/tests/test_enhanced_list_view.js`
- `docs/LIST_VIEW_CLOUD_DEPLOYMENT.md`

These changes are **uncommitted and not pushed**. The previously committed source
fix alone does not include this asset-loading correction. No new release SHA is
claimed. Preserve the unrelated, uncommitted VAT report work in this checkout.
An authorized maintainer must commit only the listed files, record the resulting
SHA, and publish it through the app's existing review/release workflow.

## Frappe Cloud Handoff

No authenticated Cloud control-plane or production Desk session is available in
this environment. The exact production bench group, public/private status,
configured app branch and deployed revision are therefore **unconfirmed**. No
production shell, build, cache command or deployment has been executed.

1. In Frappe Cloud, open the site record serving `qatra.k.frappe.cloud`. Record its
   actual bench group and site identifier. Inspect Apps and the active Deploy's
   app-version details to confirm the repository, configured branch and SHA for
   construction_management. Do not change its branch merely to match local.
2. Publish the scoped correction through that branch's established workflow.
   It must include the width-only source fix `0c43246...` and the newly committed
   bundle/hook change. If the configured branch is not `test-pankaj`, merge or
   cherry-pick the scoped change through normal review rather than deploying
   unrelated working-tree changes. Record the actual resulting release SHA.
3. For a confirmed private bench group, use **Show Updates / Update Available**,
   select construction_management, then **Deploy and Update** with this site
   selected. Verify that app asset build succeeds and the site is moved to the
   new deployment, not merely that a bench build was created. If the site is on
   a shared/managed setup without these controls, have its Cloud operator/support
   perform the release. Do not assume SSH access or run local commands against
   an imagined production bench.
4. Confirm the completed Deploy's app versions include the recorded release SHA.
   Clear the relevant site's cache through the available supported Cloud action
   or, as an authenticated Desk administrator, use the native **Reload** command
   (the installed implementation calls `frappe.sessions.clear` and reloads).
   If a bench console is actually available, the equivalent command is
   `bench --site <exact-site-identifier-from-dashboard> clear-cache`.
5. Open a fresh Desk page or hard-reload with browser cache disabled. The new
   hashed bundle URLs must be loaded once each; neither original unversioned
   enhanced_list_view URL should still be included in Desk. A server cache clear
   alone cannot invalidate a year-long immutable browser response at the old URL.

This change needs an asset build, not a schema patch or custom migration. The
Cloud platform's normal deployment/site-update lifecycle should be allowed to
complete; no manual core modifications or broad cache deletion are required.

References: [Frappe asset bundling](https://docs.frappe.io/framework/user/en/basics/asset-bundling),
[Cloud bench updates and deployed app versions](https://docs.frappe.io/cloud/benches/updating_a_bench),
[private-bench site update workflow](https://docs.frappe.io/cloud/sites/how-to-update-an-app-site-on-a-private-bench).

## Verification and Acceptance

Local commands completed:

```sh
bench build --app construction_management
bench --site Qatra.local clear-cache
node apps/construction_management/construction_management/tests/test_enhanced_list_view.js
```

The actual compiled JS/CSS were additionally passed to the same headless Chrome
test using `LIST_RESIZE_SCRIPT` and `LIST_RESIZE_CSS` environment variables. Both
tests passed. The browser fixture uses installed native header rendering and Desk
CSS for Sales Invoice, Purchase Invoice and Customer; it checks native typography,
row height/spacing, checkboxes, status indicators, links, sorting, minimum widths,
grow/shrink, header/cell alignment, horizontal scrolling, cancellation, refresh,
filter/page re-renders, route persistence, per-user isolation and child-grid drag
isolation. Loading the script twice also leaves exactly one handle per eligible
header and one effective patch. Screenshot: `/tmp/qatra-list-widths-bundled.png`.
This is a browser fixture, not an authenticated production List View test.

The local manifest currently resolves JS to
`/assets/construction_management/dist/js/construction_list_view.bundle.PETLITO3.js`
and CSS to
`/assets/construction_management/dist/css/construction_list_view.bundle.E36C62Q6.css`.
Build environments can produce different hashes; verify their current manifest,
not these literal hashes as a production contract. Built assets/manifest are
deployment outputs, not additional source files to commit.

After production deployment, verify Sales Invoice and Purchase Invoice:

1. Network shows one hashed List View JS and one hashed CSS, no old raw inclusion,
   no 404s, and JS contains `__cmelv_widths_only` / `cmelv-resize-line` but no
   custom Drag badge/reordering code.
2. Header boundaries show thin lines and a col-resize cursor; drag grows/shrinks
   the corresponding header and every row cell with no sorting or navigation.
3. Normal sorting, selection, document links and status indicators still work.
   Wide columns scroll within the list; native typography and row heights remain.
4. Refresh, apply/remove a filter, navigate to the other DocType and back. No badge
   reappears, handles do not multiply, and each user's saved widths restore.
5. If Drag controls remain after confirmed hashed assets and a fresh page load,
   inspect enabled **production** Client Scripts and DevTools Sources/DOM mutation
   call stacks for the actual injecting script. Remove its obsolete integration
   at source; do not add a second patch or merely hide its markup.

Production deployment, production Client Script inspection, and authenticated
production UI acceptance remain pending until access is provided.
