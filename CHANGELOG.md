# Changelog

## [3.0.0](https://github.com/homeylab/bookstack-file-exporter/compare/v2.3.0...v3.0.0) (2026-07-06)


### ⚠ BREAKING CHANGES

* group retention by export level and completeness; remove prune_on_partial ([#164](https://github.com/homeylab/bookstack-file-exporter/issues/164))
* a self-signed or internal-CA BookStack now fails with a TLS verification error on first run. Set http_config.verify_ssl: false, or point the REQUESTS_CA_BUNDLE environment variable at your CA bundle, to opt out.
* reject explicit YAML null for config fields with defaults ([#155](https://github.com/homeylab/bookstack-file-exporter/issues/155))
* boto3 object-storage client + flat S3 schema (v3.0.0) ([#149](https://github.com/homeylab/bookstack-file-exporter/issues/149))
* the 'minio:' config key is removed; use 'object_storage:'.

### Features

* add CLI exit codes and graceful scheduled-mode lifecycle ([#133](https://github.com/homeylab/bookstack-file-exporter/issues/133)) ([a081024](https://github.com/homeylab/bookstack-file-exporter/commit/a081024a4076903eb8a55bf24ebc680eaec3d70a))
* add opt-in JSON-structured logging toggle ([#135](https://github.com/homeylab/bookstack-file-exporter/issues/135)) ([d8fe5f2](https://github.com/homeylab/bookstack-file-exporter/commit/d8fe5f2581c8b9a27fdbc3f4dbb859c52f060437))
* boto3 object-storage client + flat S3 schema (v3.0.0) ([#149](https://github.com/homeylab/bookstack-file-exporter/issues/149)) ([505e03c](https://github.com/homeylab/bookstack-file-exporter/commit/505e03cb658ad93b9ecd7c8eceebccb1f272e93a))
* cron schedule (run_schedule) for daemon mode ([#136](https://github.com/homeylab/bookstack-file-exporter/issues/136)) ([911a34f](https://github.com/homeylab/bookstack-file-exporter/commit/911a34f4ab4ca903c4d1790952aef0d5aaf0549b))
* group retention by export level and completeness; remove prune_on_partial ([#164](https://github.com/homeylab/bookstack-file-exporter/issues/164)) ([ffd8fa8](https://github.com/homeylab/bookstack-file-exporter/commit/ffd8fa8c261635a96f1c021233f7a7aa3f9c72dd))
* grouped failure bullets + opt-in markdown notification body ([#151](https://github.com/homeylab/bookstack-file-exporter/issues/151)) ([2e3f320](https://github.com/homeylab/bookstack-file-exporter/commit/2e3f32070d1d3b346e85bcb7c4d761a7cfba2c25))
* honor export_images/export_attachments standalone at book/chapter level ([#134](https://github.com/homeylab/bookstack-file-exporter/issues/134)) ([cd13e48](https://github.com/homeylab/bookstack-file-exporter/commit/cd13e48c2de28ad54ea278f5693e6e05b6540a52))
* opt-in /healthz health server for scheduled mode ([#137](https://github.com/homeylab/bookstack-file-exporter/issues/137)) ([4b4949f](https://github.com/homeylab/bookstack-file-exporter/commit/4b4949fd69c6ee22256ccc1336a1a6686395e439))
* opt-in export_workers for parallel node fetch ([#140](https://github.com/homeylab/bookstack-file-exporter/issues/140)) ([881fb74](https://github.com/homeylab/bookstack-file-exporter/commit/881fb7417a5a5220d448842471dcf21910c95b0f))
* pre-v3 improvements — cleanup-failure PARTIAL, parallel uploads, is_aws single-sourcing ([#150](https://github.com/homeylab/bookstack-file-exporter/issues/150)) ([5dd9533](https://github.com/homeylab/bookstack-file-exporter/commit/5dd9533e2e82c1c35f3eab51b7678fd825b021b3))
* production-grade graceful shutdown for scheduled mode ([#138](https://github.com/homeylab/bookstack-file-exporter/issues/138)) ([6e12ae3](https://github.com/homeylab/bookstack-file-exporter/commit/6e12ae3cb6f41814378c23f79119ab143b19292a))
* report archive path and destinations in success notification ([#121](https://github.com/homeylab/bookstack-file-exporter/issues/121)) ([ac6db62](https://github.com/homeylab/bookstack-file-exporter/commit/ac6db624fbbff1996735c227e0e82b6ed84c79b9))
* report partial runs on content loss and hard-fail when no documents were archived ([#153](https://github.com/homeylab/bookstack-file-exporter/issues/153)) ([8ab0703](https://github.com/homeylab/bookstack-file-exporter/commit/8ab0703174ba801e038282af4195139b1d681295))
* S3 upload support via object_storage list (v3.0.0) ([#142](https://github.com/homeylab/bookstack-file-exporter/issues/142)) ([633ded5](https://github.com/homeylab/bookstack-file-exporter/commit/633ded5a576a7a31eac23b9e0907f320bc494625))
* silence cancelled runs and report nothing-to-archive runs honestly ([#156](https://github.com/homeylab/bookstack-file-exporter/issues/156)) ([0a46a83](https://github.com/homeylab/bookstack-file-exporter/commit/0a46a837f796cfb40472aed0a0922b201750aaa2))
* stream exports directly into the final gzipped archive ([#158](https://github.com/homeylab/bookstack-file-exporter/issues/158)) ([eddaf59](https://github.com/homeylab/bookstack-file-exporter/commit/eddaf5930323d211c035b864c5bc289732f158db))
* support LOG_LEVEL env var for log level ([#147](https://github.com/homeylab/bookstack-file-exporter/issues/147)) ([80f72f0](https://github.com/homeylab/bookstack-file-exporter/commit/80f72f077a3b26b4935d9f51b8f80eb5507c1236))
* UTC timestamps, fail-fast archive errors, and per-target TLS options for object storage ([#159](https://github.com/homeylab/bookstack-file-exporter/issues/159)) ([040cf40](https://github.com/homeylab/bookstack-file-exporter/commit/040cf407fd1d8a1ebac843ed446263231e45f168))


### Bug Fixes

* clearer one-shot run summary wording ([#167](https://github.com/homeylab/bookstack-file-exporter/issues/167)) ([89e06ea](https://github.com/homeylab/bookstack-file-exporter/commit/89e06ea39db22f1daa828d7d55ebb699dae7b00c))
* fetch secure-storage images via authenticated API (issue [#145](https://github.com/homeylab/bookstack-file-exporter/issues/145)) ([#162](https://github.com/homeylab/bookstack-file-exporter/issues/162)) ([fafc2cc](https://github.com/homeylab/bookstack-file-exporter/commit/fafc2cc94ad23169124090b3eb839d4fa92c5d21))
* honor shutdown signals promptly in one-shot parallel export ([#157](https://github.com/homeylab/bookstack-file-exporter/issues/157)) ([2b8eae3](https://github.com/homeylab/bookstack-file-exporter/commit/2b8eae39f59e6c753d9ba13877ef7af3bde69c7f))
* notification and config crash-class bugs ([#152](https://github.com/homeylab/bookstack-file-exporter/issues/152)) ([c5e9586](https://github.com/homeylab/bookstack-file-exporter/commit/c5e9586e8bc9687e7f3597ab40db57a9cc124d02))
* raise clear error on empty config file ([#126](https://github.com/homeylab/bookstack-file-exporter/issues/126)) ([11c6b00](https://github.com/homeylab/bookstack-file-exporter/commit/11c6b0070629d91343cea78bb4c67243c9853b4a))
* reject explicit YAML null for config fields with defaults ([#155](https://github.com/homeylab/bookstack-file-exporter/issues/155)) ([3f34206](https://github.com/homeylab/bookstack-file-exporter/commit/3f34206df85f96969f8f52395a9d6bb06610b9b3))
* resolve apprise urls in one validated env probe ([#125](https://github.com/homeylab/bookstack-file-exporter/issues/125)) ([be1bf23](https://github.com/homeylab/bookstack-file-exporter/commit/be1bf230b723dc680011d3bf44163b376ea8bc8a))
* retention ordering, entrypoint exec, and apprise asset propagation ([#154](https://github.com/homeylab/bookstack-file-exporter/issues/154)) ([59ba365](https://github.com/homeylab/bookstack-file-exporter/commit/59ba3651405f669970d158f0089844bcd02410f1))
* v3.0.0 pre-release hardening — correctness, lifecycle, notification sanitizer, and run summary ([#160](https://github.com/homeylab/bookstack-file-exporter/issues/160)) ([1d127ea](https://github.com/homeylab/bookstack-file-exporter/commit/1d127eacbbe53d8e3e3d5bd72d0b3d305050d2d8))


### Documentation

* modernize + trim example config for v3 schema ([#148](https://github.com/homeylab/bookstack-file-exporter/issues/148)) ([19b79b7](https://github.com/homeylab/bookstack-file-exporter/commit/19b79b7cf534a323a70f897d68e146104a8e23f3))
* note README tracks main, point to release tags for versioned docs ([#141](https://github.com/homeylab/bookstack-file-exporter/issues/141)) ([8b5623c](https://github.com/homeylab/bookstack-file-exporter/commit/8b5623c6a004d0c9354ff532bc7db4e932cdbbf1))
* split README into docs/ topic pages + add CONTRIBUTING ([#146](https://github.com/homeylab/bookstack-file-exporter/issues/146)) ([7544ced](https://github.com/homeylab/bookstack-file-exporter/commit/7544cedeefe6e4d303d5d185f5e3c730bcf42251))
* sync 2.4.0 feature docs for health endpoint and notifications ([#139](https://github.com/homeylab/bookstack-file-exporter/issues/139)) ([e270768](https://github.com/homeylab/bookstack-file-exporter/commit/e270768ecdedfb32d14807c283905b945a84a2f5))
* v3 pre-release doc polish + image-fetch terminology ([#163](https://github.com/homeylab/bookstack-file-exporter/issues/163)) ([569eb5b](https://github.com/homeylab/bookstack-file-exporter/commit/569eb5b869c8c5ae25891a900e2021f15ff18c7e))
* v3 pre-release review — add operations guide, tighten v2→v3 accuracy ([#166](https://github.com/homeylab/bookstack-file-exporter/issues/166)) ([4ba1d7d](https://github.com/homeylab/bookstack-file-exporter/commit/4ba1d7ddfa22eb4799891ad36b3c97fb0e506361))

## [2.3.0](https://github.com/homeylab/bookstack-file-exporter/compare/v2.2.0...v2.3.0) (2026-06-15)


### Features

* regex filter for shelves/books/chapters/pages export ([#72](https://github.com/homeylab/bookstack-file-exporter/issues/72)) ([#116](https://github.com/homeylab/bookstack-file-exporter/issues/116)) ([ccb9515](https://github.com/homeylab/bookstack-file-exporter/commit/ccb95154fbb9bef4eeae92c471a9ae5a2e2e399b))

## [2.2.0](https://github.com/homeylab/bookstack-file-exporter/compare/v2.1.0...v2.2.0) (2026-06-06)


### Features

* add export_level for book and chapter exports ([#73](https://github.com/homeylab/bookstack-file-exporter/issues/73)) ([e639991](https://github.com/homeylab/bookstack-file-exporter/commit/e63999149d35b067a9543053bda02a53f54344c4))
* add export_level for book and chapter exports ([#73](https://github.com/homeylab/bookstack-file-exporter/issues/73)) ([58dde6b](https://github.com/homeylab/bookstack-file-exporter/commit/58dde6b2782f795cc28064d02026b47e78e7ac1a))
* descendant-page name map for book/chapter nodes ([0803e07](https://github.com/homeylab/bookstack-file-exporter/commit/0803e0708a839c0a16cad1b29124f7c26817d52c))
* enable modify_links for books/chapters export levels ([68eaaac](https://github.com/homeylab/bookstack-file-exporter/commit/68eaaac526485df97955855a77cb979037735be9))
* folder-per-node layout for books/chapters export ([f9779ab](https://github.com/homeylab/bookstack-file-exporter/commit/f9779ab9369879bda17f153037b982b3e331de8f))
* lift asset download into NodeArchiver base ([1dedb3f](https://github.com/homeylab/bookstack-file-exporter/commit/1dedb3f4a8eca31bb574784fb76aca6f4775a787))
* localize html img-src for pages and book/chapter exports ([40851a1](https://github.com/homeylab/bookstack-file-exporter/commit/40851a1c9130643a60113e8585098694e07184e0))
* localize images/attachments in book/chapter markdown ([4128c03](https://github.com/homeylab/bookstack-file-exporter/commit/4128c0392e65a5642d426223fd58d02b8ca38b44))
* move asset config into NodeArchiver base ([72b1273](https://github.com/homeylab/bookstack-file-exporter/commit/72b1273d7a0f407c33677463fa7c72b705eaac90))
* slim inline base64 img-src by reusing downloaded anchor asset ([09dc01b](https://github.com/homeylab/bookstack-file-exporter/commit/09dc01b3ffc061ef965d16f2d873f9d70ebd78ea))


### Bug Fixes

* add archive timestamp-suffix format test ([0e2315a](https://github.com/homeylab/bookstack-file-exporter/commit/0e2315aa49a985d8a07f4da22cc6fdb0632d1fcc))
* clarify check_var required semantics and return type ([2e9f4ec](https://github.com/homeylab/bookstack-file-exporter/commit/2e9f4ec552ec17bc7866f9992da0e27faacb4f41))
* code review remediation (bug fixes, DRY, tests) ([33c8d12](https://github.com/homeylab/bookstack-file-exporter/commit/33c8d12261d9d999bfcbd223355b6ba49f489e0c))
* deduplicate asset page-grouping logic ([f470062](https://github.com/homeylab/bookstack-file-exporter/commit/f47006272ef8f4fae5a541b00c3c2dfcfa6f9f06))
* invoke minio config validator in is_valid ([0524472](https://github.com/homeylab/bookstack-file-exporter/commit/0524472fb4762b59d24b1444dd2b692e785fa2db))
* modernize type hints to PEP 585 via pyupgrade ([a23903c](https://github.com/homeylab/bookstack-file-exporter/commit/a23903c8b7149e5416f426916cd3cf82b3685c39))
* normalize trailing slashes with rstrip ([01870a1](https://github.com/homeylab/bookstack-file-exporter/commit/01870a1f55f8cea030e061016d8dda0ada1db8bf))
* raise on unknown asset type in get_asset_bytes ([65f7035](https://github.com/homeylab/bookstack-file-exporter/commit/65f70357ec8b05de878c044015ac8db8400722e3))
* remove broken verify_ssl property from PageArchiver ([f24f4f1](https://github.com/homeylab/bookstack-file-exporter/commit/f24f4f11f7b4e7f7cac05afe3fee9d2dd3ac936d))
* remove commented-out dead code ([dac95eb](https://github.com/homeylab/bookstack-file-exporter/commit/dac95eb3f4ccf344093f7a915d06996df5fbc61f))
* remove unreachable run call in entrypoint loop ([c1fcf8b](https://github.com/homeylab/bookstack-file-exporter/commit/c1fcf8ba2548534edbbaa568552cd3683518b3c2))
* resolve pre-existing test lint findings ([f0b9c3a](https://github.com/homeylab/bookstack-file-exporter/commit/f0b9c3a1d0821d068ec2cd6a14661c058a873f55))
* reuse a single requests Session in HttpHelper ([3d8afb0](https://github.com/homeylab/bookstack-file-exporter/commit/3d8afb09ecf4c14cf2da5e9acf5803677ac30067))
* stop API Session echoing BookStack session cookie ([8cbe16a](https://github.com/homeylab/bookstack-file-exporter/commit/8cbe16adee6db567d0671af9e65e7680879168c1))
* trim trailing newlines in page_archiver ([aa93486](https://github.com/homeylab/bookstack-file-exporter/commit/aa934869808bf1b97e8ac8b7b4ea55088ae90c63))
* use dict.update for node map merges ([a56a07b](https://github.com/homeylab/bookstack-file-exporter/commit/a56a07b82b14b19eceb8718aea6478256f251a87))


### Documentation

* address counter-review (chapter walk blocker, dead-state warn, fixture tests) ([ac0ba8a](https://github.com/homeylab/bookstack-file-exporter/commit/ac0ba8a4d44990b79127251576dc4bd5c92134de))
* correct modify_links html behavior for scaled + base64 img-src ([f3373e8](https://github.com/homeylab/bookstack-file-exporter/commit/f3373e86ed08f17b40ca0b101e0008c31cc8ec38))
* correct modify_links html behavior for scaled + base64 img-src ([f62c6cb](https://github.com/homeylab/bookstack-file-exporter/commit/f62c6cbc87b03bee68b0c98360d2cdfc61a70cd7))
* drop superseded planning docs (handoff plan is source of truth) ([421e991](https://github.com/homeylab/bookstack-file-exporter/commit/421e9918f9ffe81604e55b1e79106bbd17d211f4))
* extend modify_links scope to html (remote src/href survive combined html) ([2056dfa](https://github.com/homeylab/bookstack-file-exporter/commit/2056dfa61f2a0c6ebacca0290da84f5ef0cd08ba))
* implementation plan for modify_links book/chapter ([d4f9c7d](https://github.com/homeylab/bookstack-file-exporter/commit/d4f9c7dfac3e973778e211ce881422f078fc0227))
* modify_links + folder layout for books/chapters ([0c07407](https://github.com/homeylab/bookstack-file-exporter/commit/0c07407ff6674f2b7f28b32b64f411df84ba5629))
* spec modify_links for book/chapter markdown + folder layout ([4a8c309](https://github.com/homeylab/bookstack-file-exporter/commit/4a8c309272c736cd27c6942f6a82c74e66e0bce6))
