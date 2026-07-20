# Changelog

All notable changes to this project are documented here.
## [0.9.1] - 2026-07-20

### Added

- Print progress lines for the asset heal and full table rebuild ([f2f6506](https://github.com/trenchtoaster/deadlock-matches/commit/f2f6506f60c3dc656836ce02b7c410426d86a001))


## [0.9.0] - 2026-07-20

### Added

- Handle API rate limits and report per-match download progress ([bae9c9c](https://github.com/trenchtoaster/deadlock-matches/commit/bae9c9cc706a5bf9a219d67cdf6da275a4883229))

- Keep one body per match and resolve archive lookups in one scan ([211776c](https://github.com/trenchtoaster/deadlock-matches/commit/211776c40fb5524ea8721360f7685d21337c6633))


### Documentation

- Cover the archive body rules and rate limit handling in the skill ([0678252](https://github.com/trenchtoaster/deadlock-matches/commit/067825278e3150313c8a38da1bfdb426e1393faa))


## [0.8.1] - 2026-07-19

### Internal

- Deduplicate interval logic ([f0204fa](https://github.com/trenchtoaster/deadlock-matches/commit/f0204fadfcea7ffab2f0318b38960c0cd4055b94))


## [0.8.0] - 2026-07-18

### Added

- Add source_totals and enemy_damage_totals helpers ([888a836](https://github.com/trenchtoaster/deadlock-matches/commit/888a83679bb97cfec3b834fa9f9c00669b879a3a))


### Documentation

- Call the installed deadlock command in the skill and docs ([fd28669](https://github.com/trenchtoaster/deadlock-matches/commit/fd28669ee48454627f979f200b2c843eb10bd655))


### Internal

- Split queries into a package with one module per report area, tests mirrored ([2acd211](https://github.com/trenchtoaster/deadlock-matches/commit/2acd211acca0910811a6106c00a263a7ea193fd6))


## [0.7.0] - 2026-07-16

### Added

- Rework compare into source and timeline reports ([d2b6c2c](https://github.com/trenchtoaster/deadlock-matches/commit/d2b6c2c90ed5895e144f0cf71156dc812e97f6a7))


### Documentation

- Update compare source totals ([19418df](https://github.com/trenchtoaster/deadlock-matches/commit/19418df867e8c4aea7a53c3b68e41456dab37251))


### Fixed

- Asset tables missing from a store fall back to the main export copy so the players tables share them ([af33e7e](https://github.com/trenchtoaster/deadlock-matches/commit/af33e7e346d465549a44e4a7696f25367a2b6140))

- Organize command docs and leaderboard output ([543aece](https://github.com/trenchtoaster/deadlock-matches/commit/543aece44aa82d03efcc491173c550867fb8d788))


## [0.6.0] - 2026-07-15

### Added

- Rebuilt movement as an archive command and moved the tracked comparison to compare --stat movement ([b1a4837](https://github.com/trenchtoaster/deadlock-matches/commit/b1a4837f6f974400fe17fd4aa627ac228fec3cd7))


## [0.5.0] - 2026-07-15

### Added

- Added a damage command that splits damage to heroes by gun, abilities, and item procs across every game ([87246fa](https://github.com/trenchtoaster/deadlock-matches/commit/87246fa73342d9048654781eecd24fe86524e7c3))

- Added a healing command splitting your healing by source, with the share that lands on you vs teammates ([bd26e45](https://github.com/trenchtoaster/deadlock-matches/commit/bd26e45707eb33281cc99ee72462c9ce5f19d206))

- Added souls and combat commands and new rate columns across the damage and healing tables ([a2dc43f](https://github.com/trenchtoaster/deadlock-matches/commit/a2dc43f5a4f6860c0c002a96e476dd01911a16f2))

- Sync now heals the asset tables after a patch ([42b75e9](https://github.com/trenchtoaster/deadlock-matches/commit/42b75e9081a6ca3d42849af640b8399951a6c7f7))


## [0.4.0] - 2026-07-13

### Added

- Added a --melee view to the match command ([4fd68b7](https://github.com/trenchtoaster/deadlock-matches/commit/4fd68b7e2e75f0815232e547561afbba5304ee1c))

- Added the as-of era note to the item and ability cards ([8d34a05](https://github.com/trenchtoaster/deadlock-matches/commit/8d34a0526d88fa0ed64b00fb53410f9af00bfdbf))

- Fixed the plurals in the sync output and made config say when nothing is excluded ([15d4e3f](https://github.com/trenchtoaster/deadlock-matches/commit/15d4e3f8c8b533fb0b6be6ca16b818a0d68c5768))

- Added a skill command to install the bundled Claude Code skill ([bc10464](https://github.com/trenchtoaster/deadlock-matches/commit/bc10464009c5b29fb6230f0bb7386bd8af4514b4))

- Made --kills and --deaths count kills per enemy and moved the damage taken table to --damage ([fa1145d](https://github.com/trenchtoaster/deadlock-matches/commit/fa1145d3b63473a1cf3c2cb24f55bd90085492aa))


### Documentation

- Moved the command reference out of the README into docs/ ([c777378](https://github.com/trenchtoaster/deadlock-matches/commit/c7773782c1a9c301eabc3d1bdd52c1f32f20092a))

- Gave sync, history, and --source api their own copy-paste blocks in the README ([34c5bad](https://github.com/trenchtoaster/deadlock-matches/commit/34c5badb203332222984e03c3b5cdd9d1afa8aa9))


## [0.3.0] - 2026-07-12

### Added

- Put config.toml in the user config directory with a config command ([4e35538](https://github.com/trenchtoaster/deadlock-matches/commit/4e355386f61b0079e8b61aaeac8f6a0a687f59bf))


## [0.2.1] - 2026-07-12

### Fixed

- Show history for deadlock with no sub-command instead of crashing ([fac8d07](https://github.com/trenchtoaster/deadlock-matches/commit/fac8d0709bdd4f3cd146367378a5ed60549094b2))


## [0.2.0] - 2026-07-12

### Added

- Resolve config and asset data to user directories when installed ([0073d90](https://github.com/trenchtoaster/deadlock-matches/commit/0073d90da0609f1f68161eeb303f9e5e30eed6c4))


## [0.1.0] - 2026-07-12

### Added

- Initial release with local match archive reading, protobuf decoding, parquet export, CLI reports, reusable Polars queries, Deadlock assets, and tracked-player downloads.

