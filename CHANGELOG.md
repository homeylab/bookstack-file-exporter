# Changelog

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
