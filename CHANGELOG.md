# Changelog

All notable changes to this project are documented here.
## [0.12.0] - 2026-07-31

### Added

- Support the 2026-07-30 matchmaking update ([97302a4](https://github.com/trenchtoaster/deadlock-matches/commit/97302a4c126bec7c8b1c5f89552db9446e91639b))


## [0.11.0] - 2026-07-29

### Added

- Add codex and gemini targets to skill install ([ca05485](https://github.com/trenchtoaster/deadlock-matches/commit/ca05485f40c0c5065fc0ebbe3c979efd3c717cf1))

- Report the live data build in assets ([2eb1131](https://github.com/trenchtoaster/deadlock-matches/commit/2eb11316a62607ce87ca6c3f5b87d2449226a20d))


## [0.10.0] - 2026-07-28

### Added

- Add hero-level combat records ([87edb7e](https://github.com/trenchtoaster/deadlock-matches/commit/87edb7e78fdf4129f8b13dd9ba73746bc1c76a30))

- Add metric views ([dd45079](https://github.com/trenchtoaster/deadlock-matches/commit/dd450796c2949c75f26fb6070c1c1362c9bb48e5))

- Migrate comparison reports to metric views ([12528a4](https://github.com/trenchtoaster/deadlock-matches/commit/12528a4d2405e12898e48bdda7eef0818a3fd9e1))

- Name the metric views in the schema listing ([358f904](https://github.com/trenchtoaster/deadlock-matches/commit/358f904348e690dd31c98024c43a425796b0ed80))

- Scope reports to normal matchmaking with mode flags ([687ddba](https://github.com/trenchtoaster/deadlock-matches/commit/687ddba2a3536b85ea003d69e64eec552aafa33f))

- Store tables hive-partitioned with start_time and hero_id ([1a22c93](https://github.com/trenchtoaster/deadlock-matches/commit/1a22c9319f1c33724c63cba7bd6f800e7a983b29))

- Add winrate --by mode for a per-mode record ([2d68baa](https://github.com/trenchtoaster/deadlock-matches/commit/2d68baac764f87938600f5ad2dabad7f61dc4f52))


### Documentation

- Update docs and add information about metric views ([6cdf926](https://github.com/trenchtoaster/deadlock-matches/commit/6cdf926753ef90c5b39a143c0d08932677c9fdb2))

- Document the mode flags and the matchmaking default ([83dddda](https://github.com/trenchtoaster/deadlock-matches/commit/83dddda5298a7f8e6a8aa8ec80ec212837e63b31))

- Cover mode filtering in the catalog and caveats ([d4a7551](https://github.com/trenchtoaster/deadlock-matches/commit/d4a7551a160d94c96095c14dd81d0859ad089ee9))


### Fixed

- Install schema caveat references ([bb3b161](https://github.com/trenchtoaster/deadlock-matches/commit/bb3b16166f14ff4391d2f9c7ccf183dff5c7b328))

- Derive current asset labels at read time ([9379fe9](https://github.com/trenchtoaster/deadlock-matches/commit/9379fe964d085281d299ae367598e449f9393259))

- Read the last stats snapshot instead of the biggest ([a912a39](https://github.com/trenchtoaster/deadlock-matches/commit/a912a39c15c285214f8191b9e128d8af27921811))

- Count UnknownAbility as a detail row, not a total ([c6b5659](https://github.com/trenchtoaster/deadlock-matches/commit/c6b565964ccb35a091822480547e161a151bfad5))


### Internal

- Moved soul, lane, objective, and buff labels to read time ([bc47087](https://github.com/trenchtoaster/deadlock-matches/commit/bc470872dd1cdcff38255f5bbbf387da94d5644a))


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

