# Valve protos

These schema files describe Valve's match metadata messages and come from [SteamDatabase/Protobufs](https://github.com/SteamDatabase/Protobufs). They are copyright Valve Corporation and are included for interoperability, so the tool can read the match files already on your computer.

The generated code in `src/deadlock_matches/gen/` is compiled from these files and is checked in, so a user never needs to run protoc.

To refresh it, fetch each file of the compile closure from `https://raw.githubusercontent.com/SteamDatabase/Protobufs/master/deadlock/<file>.proto`, diff it against the copy here, and run `just protos`. The closure is `citadel_gcmessages_common`, `base_gcmessages`, `gcsdk_gcmessages`, `steammessages`, `valveextensions`, `steammessages_steamlearn.steamworkssdk`, and `steammessages_unified_base.steamworkssdk`. The other files here are not compiled.

The recipe uses grpcio-tools from the dev group. It prints the `Protobuf Python Version` the gencode stamps, and that version must not be newer than the `protobuf` floor in `pyproject.toml`, because the gencode checks the runtime version on import. Raise the floor when the generator moves past it.

Valve renames enum values now and then (`k_ECitadelRankedType_*` became `k_eCitadelRankedType_*`). After a refresh, grep the source for every enum prefix it strips, since a stale prefix only leaves the label unstripped and raises nothing.
