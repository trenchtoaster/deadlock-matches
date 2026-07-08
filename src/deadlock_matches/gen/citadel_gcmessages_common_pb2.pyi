import steammessages_pb2 as _steammessages_pb2
import gcsdk_gcmessages_pb2 as _gcsdk_gcmessages_pb2
import base_gcmessages_pb2 as _base_gcmessages_pb2
import valveextensions_pb2 as _valveextensions_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CMsgLaneColor(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ELaneColor_Invalid: _ClassVar[CMsgLaneColor]
    k_ELaneColor_Yellow: _ClassVar[CMsgLaneColor]
    k_ELaneColor_Green: _ClassVar[CMsgLaneColor]
    k_ELaneColor_Blue: _ClassVar[CMsgLaneColor]
    k_ELaneColor_Purple: _ClassVar[CMsgLaneColor]

class EGCCitadelCommonMessages(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_EMsgAnyToGCReportAsserts: _ClassVar[EGCCitadelCommonMessages]
    k_EMsgAnyToGCReportAssertsResponse: _ClassVar[EGCCitadelCommonMessages]

class ECitadelMatchMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelMatchMode_Invalid: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_Unranked: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_PrivateLobby: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_CoopBot: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_Ranked: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_ServerTest: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_Tutorial: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_HeroLabs: _ClassVar[ECitadelMatchMode]
    k_ECitadelMatchMode_Calibration: _ClassVar[ECitadelMatchMode]

class ECitadelLobbyTeam(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelLobbyTeam_Team0: _ClassVar[ECitadelLobbyTeam]
    k_ECitadelLobbyTeam_Team1: _ClassVar[ECitadelLobbyTeam]
    k_ECitadelLobbyTeam_Spectator: _ClassVar[ECitadelLobbyTeam]

class ECitadelAccountStatMedal(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eNone: _ClassVar[ECitadelAccountStatMedal]
    k_eBronze: _ClassVar[ECitadelAccountStatMedal]
    k_eSilver: _ClassVar[ECitadelAccountStatMedal]
    k_eGold: _ClassVar[ECitadelAccountStatMedal]

class ECitadelMMPreference(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelMMPreference_Invalid: _ClassVar[ECitadelMMPreference]
    k_ECitadelMMPreference_Casual: _ClassVar[ECitadelMMPreference]
    k_ECitadelMMPreference_Serious: _ClassVar[ECitadelMMPreference]

class ECitadelObjective(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eCitadelObjective_Team0_Core: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier1_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier1_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier1_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier1_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier2_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier2_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier2_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Tier2_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_Titan: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_TitanShieldGenerator_1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_TitanShieldGenerator_2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_BarrackBoss_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_BarrackBoss_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_BarrackBoss_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team0_BarrackBoss_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Core: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier1_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier1_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier1_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier1_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier2_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier2_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier2_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Tier2_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_Titan: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_TitanShieldGenerator_1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_TitanShieldGenerator_2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_BarrackBoss_Lane1: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_BarrackBoss_Lane2: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_BarrackBoss_Lane3: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Team1_BarrackBoss_Lane4: _ClassVar[ECitadelObjective]
    k_eCitadelObjective_Neutral_Mid: _ClassVar[ECitadelObjective]

class ECitadelTeamObjective(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eCitadelTeamObjective_Core: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier1_Lane1: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier1_Lane2: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier1_Lane3: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier1_Lane4: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier2_Lane1: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier2_Lane2: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier2_Lane3: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Tier2_Lane4: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_Titan: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_TitanShieldGenerator_1: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_TitanShieldGenerator_2: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_BarrackBoss_Lane1: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_BarrackBoss_Lane2: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_BarrackBoss_Lane3: _ClassVar[ECitadelTeamObjective]
    k_eCitadelTeamObjective_BarrackBoss_Lane4: _ClassVar[ECitadelTeamObjective]

class ECitadelBotDifficulty(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelBotDifficulty_None: _ClassVar[ECitadelBotDifficulty]
    k_ECitadelBotDifficulty_Easy: _ClassVar[ECitadelBotDifficulty]
    k_ECitadelBotDifficulty_Medium: _ClassVar[ECitadelBotDifficulty]
    k_ECitadelBotDifficulty_Hard: _ClassVar[ECitadelBotDifficulty]
    k_ECitadelBotDifficulty_Nightmare: _ClassVar[ECitadelBotDifficulty]
    k_ECitadelBotDifficulty_Guided: _ClassVar[ECitadelBotDifficulty]

class ECitadelRegionMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelRegionMode_ROW: _ClassVar[ECitadelRegionMode]
    k_ECitadelRegionMode_Europe: _ClassVar[ECitadelRegionMode]
    k_ECitadelRegionMode_SEAsia: _ClassVar[ECitadelRegionMode]
    k_ECitadelRegionMode_SAmerica: _ClassVar[ECitadelRegionMode]
    k_ECitadelRegionMode_Russia: _ClassVar[ECitadelRegionMode]
    k_ECitadelRegionMode_Oceania: _ClassVar[ECitadelRegionMode]

class ECitadelLeaderboardRegion(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelLeaderboardRegion_None: _ClassVar[ECitadelLeaderboardRegion]
    k_ECitadelLeaderboardRegion_Europe: _ClassVar[ECitadelLeaderboardRegion]
    k_ECitadelLeaderboardRegion_Asia: _ClassVar[ECitadelLeaderboardRegion]
    k_ECitadelLeaderboardRegion_NAmerica: _ClassVar[ECitadelLeaderboardRegion]
    k_ECitadelLeaderboardRegion_SAmerica: _ClassVar[ECitadelLeaderboardRegion]
    k_ECitadelLeaderboardRegion_Oceania: _ClassVar[ECitadelLeaderboardRegion]

class ECitadelGameMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_ECitadelGameMode_Invalid: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_Normal: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_1v1Test: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_Sandbox: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_StreetBrawl: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_ExploreNYC: _ClassVar[ECitadelGameMode]
    k_ECitadelGameMode_Internal: _ClassVar[ECitadelGameMode]

class ELobbyServerState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eLobbyServerState_Assign: _ClassVar[ELobbyServerState]
    k_eLobbyServerState_InGame: _ClassVar[ELobbyServerState]
    k_eLobbyServerState_PostMatch: _ClassVar[ELobbyServerState]
    k_eLobbyServerState_SignedOut: _ClassVar[ELobbyServerState]
    k_eLobbyServerState_Abandoned: _ClassVar[ELobbyServerState]

class EBannedFeature(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eBannedFeature_Invalid: _ClassVar[EBannedFeature]
    k_eBannedFeature_LowPriorityMatchmaking: _ClassVar[EBannedFeature]
    k_eBannedFeature_CommsRestricted: _ClassVar[EBannedFeature]
    k_eBannedFeature_ReportingDisabled: _ClassVar[EBannedFeature]

class EFeatureBanReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_eFeatureBanReason_Invalid: _ClassVar[EFeatureBanReason]
    k_eFeatureBanReason_DevCommand: _ClassVar[EFeatureBanReason]
    k_eFeatureBanReason_ReportedByOtherPlayers: _ClassVar[EFeatureBanReason]
    k_eFeatureBanReason_MatchAbandons: _ClassVar[EFeatureBanReason]
    k_eFeatureBanReason_TooManyReportsSubmitted: _ClassVar[EFeatureBanReason]
k_ELaneColor_Invalid: CMsgLaneColor
k_ELaneColor_Yellow: CMsgLaneColor
k_ELaneColor_Green: CMsgLaneColor
k_ELaneColor_Blue: CMsgLaneColor
k_ELaneColor_Purple: CMsgLaneColor
k_EMsgAnyToGCReportAsserts: EGCCitadelCommonMessages
k_EMsgAnyToGCReportAssertsResponse: EGCCitadelCommonMessages
k_ECitadelMatchMode_Invalid: ECitadelMatchMode
k_ECitadelMatchMode_Unranked: ECitadelMatchMode
k_ECitadelMatchMode_PrivateLobby: ECitadelMatchMode
k_ECitadelMatchMode_CoopBot: ECitadelMatchMode
k_ECitadelMatchMode_Ranked: ECitadelMatchMode
k_ECitadelMatchMode_ServerTest: ECitadelMatchMode
k_ECitadelMatchMode_Tutorial: ECitadelMatchMode
k_ECitadelMatchMode_HeroLabs: ECitadelMatchMode
k_ECitadelMatchMode_Calibration: ECitadelMatchMode
k_ECitadelLobbyTeam_Team0: ECitadelLobbyTeam
k_ECitadelLobbyTeam_Team1: ECitadelLobbyTeam
k_ECitadelLobbyTeam_Spectator: ECitadelLobbyTeam
k_eNone: ECitadelAccountStatMedal
k_eBronze: ECitadelAccountStatMedal
k_eSilver: ECitadelAccountStatMedal
k_eGold: ECitadelAccountStatMedal
k_ECitadelMMPreference_Invalid: ECitadelMMPreference
k_ECitadelMMPreference_Casual: ECitadelMMPreference
k_ECitadelMMPreference_Serious: ECitadelMMPreference
k_eCitadelObjective_Team0_Core: ECitadelObjective
k_eCitadelObjective_Team0_Tier1_Lane1: ECitadelObjective
k_eCitadelObjective_Team0_Tier1_Lane2: ECitadelObjective
k_eCitadelObjective_Team0_Tier1_Lane3: ECitadelObjective
k_eCitadelObjective_Team0_Tier1_Lane4: ECitadelObjective
k_eCitadelObjective_Team0_Tier2_Lane1: ECitadelObjective
k_eCitadelObjective_Team0_Tier2_Lane2: ECitadelObjective
k_eCitadelObjective_Team0_Tier2_Lane3: ECitadelObjective
k_eCitadelObjective_Team0_Tier2_Lane4: ECitadelObjective
k_eCitadelObjective_Team0_Titan: ECitadelObjective
k_eCitadelObjective_Team0_TitanShieldGenerator_1: ECitadelObjective
k_eCitadelObjective_Team0_TitanShieldGenerator_2: ECitadelObjective
k_eCitadelObjective_Team0_BarrackBoss_Lane1: ECitadelObjective
k_eCitadelObjective_Team0_BarrackBoss_Lane2: ECitadelObjective
k_eCitadelObjective_Team0_BarrackBoss_Lane3: ECitadelObjective
k_eCitadelObjective_Team0_BarrackBoss_Lane4: ECitadelObjective
k_eCitadelObjective_Team1_Core: ECitadelObjective
k_eCitadelObjective_Team1_Tier1_Lane1: ECitadelObjective
k_eCitadelObjective_Team1_Tier1_Lane2: ECitadelObjective
k_eCitadelObjective_Team1_Tier1_Lane3: ECitadelObjective
k_eCitadelObjective_Team1_Tier1_Lane4: ECitadelObjective
k_eCitadelObjective_Team1_Tier2_Lane1: ECitadelObjective
k_eCitadelObjective_Team1_Tier2_Lane2: ECitadelObjective
k_eCitadelObjective_Team1_Tier2_Lane3: ECitadelObjective
k_eCitadelObjective_Team1_Tier2_Lane4: ECitadelObjective
k_eCitadelObjective_Team1_Titan: ECitadelObjective
k_eCitadelObjective_Team1_TitanShieldGenerator_1: ECitadelObjective
k_eCitadelObjective_Team1_TitanShieldGenerator_2: ECitadelObjective
k_eCitadelObjective_Team1_BarrackBoss_Lane1: ECitadelObjective
k_eCitadelObjective_Team1_BarrackBoss_Lane2: ECitadelObjective
k_eCitadelObjective_Team1_BarrackBoss_Lane3: ECitadelObjective
k_eCitadelObjective_Team1_BarrackBoss_Lane4: ECitadelObjective
k_eCitadelObjective_Neutral_Mid: ECitadelObjective
k_eCitadelTeamObjective_Core: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier1_Lane1: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier1_Lane2: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier1_Lane3: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier1_Lane4: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier2_Lane1: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier2_Lane2: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier2_Lane3: ECitadelTeamObjective
k_eCitadelTeamObjective_Tier2_Lane4: ECitadelTeamObjective
k_eCitadelTeamObjective_Titan: ECitadelTeamObjective
k_eCitadelTeamObjective_TitanShieldGenerator_1: ECitadelTeamObjective
k_eCitadelTeamObjective_TitanShieldGenerator_2: ECitadelTeamObjective
k_eCitadelTeamObjective_BarrackBoss_Lane1: ECitadelTeamObjective
k_eCitadelTeamObjective_BarrackBoss_Lane2: ECitadelTeamObjective
k_eCitadelTeamObjective_BarrackBoss_Lane3: ECitadelTeamObjective
k_eCitadelTeamObjective_BarrackBoss_Lane4: ECitadelTeamObjective
k_ECitadelBotDifficulty_None: ECitadelBotDifficulty
k_ECitadelBotDifficulty_Easy: ECitadelBotDifficulty
k_ECitadelBotDifficulty_Medium: ECitadelBotDifficulty
k_ECitadelBotDifficulty_Hard: ECitadelBotDifficulty
k_ECitadelBotDifficulty_Nightmare: ECitadelBotDifficulty
k_ECitadelBotDifficulty_Guided: ECitadelBotDifficulty
k_ECitadelRegionMode_ROW: ECitadelRegionMode
k_ECitadelRegionMode_Europe: ECitadelRegionMode
k_ECitadelRegionMode_SEAsia: ECitadelRegionMode
k_ECitadelRegionMode_SAmerica: ECitadelRegionMode
k_ECitadelRegionMode_Russia: ECitadelRegionMode
k_ECitadelRegionMode_Oceania: ECitadelRegionMode
k_ECitadelLeaderboardRegion_None: ECitadelLeaderboardRegion
k_ECitadelLeaderboardRegion_Europe: ECitadelLeaderboardRegion
k_ECitadelLeaderboardRegion_Asia: ECitadelLeaderboardRegion
k_ECitadelLeaderboardRegion_NAmerica: ECitadelLeaderboardRegion
k_ECitadelLeaderboardRegion_SAmerica: ECitadelLeaderboardRegion
k_ECitadelLeaderboardRegion_Oceania: ECitadelLeaderboardRegion
k_ECitadelGameMode_Invalid: ECitadelGameMode
k_ECitadelGameMode_Normal: ECitadelGameMode
k_ECitadelGameMode_1v1Test: ECitadelGameMode
k_ECitadelGameMode_Sandbox: ECitadelGameMode
k_ECitadelGameMode_StreetBrawl: ECitadelGameMode
k_ECitadelGameMode_ExploreNYC: ECitadelGameMode
k_ECitadelGameMode_Internal: ECitadelGameMode
k_eLobbyServerState_Assign: ELobbyServerState
k_eLobbyServerState_InGame: ELobbyServerState
k_eLobbyServerState_PostMatch: ELobbyServerState
k_eLobbyServerState_SignedOut: ELobbyServerState
k_eLobbyServerState_Abandoned: ELobbyServerState
k_eBannedFeature_Invalid: EBannedFeature
k_eBannedFeature_LowPriorityMatchmaking: EBannedFeature
k_eBannedFeature_CommsRestricted: EBannedFeature
k_eBannedFeature_ReportingDisabled: EBannedFeature
k_eFeatureBanReason_Invalid: EFeatureBanReason
k_eFeatureBanReason_DevCommand: EFeatureBanReason
k_eFeatureBanReason_ReportedByOtherPlayers: EFeatureBanReason
k_eFeatureBanReason_MatchAbandons: EFeatureBanReason
k_eFeatureBanReason_TooManyReportsSubmitted: EFeatureBanReason

class CSOCitadelLobby(_message.Message):
    __slots__ = ("lobby_id", "match_id", "match_mode", "game_mode", "compatibility_version", "extra_messages", "server_steam_id", "server_state", "udp_connect_ip", "udp_connect_port", "sdr_address", "server_version", "safe_to_abandon", "match_punishes_abandons", "game_mode_version")
    LOBBY_ID_FIELD_NUMBER: _ClassVar[int]
    MATCH_ID_FIELD_NUMBER: _ClassVar[int]
    MATCH_MODE_FIELD_NUMBER: _ClassVar[int]
    GAME_MODE_FIELD_NUMBER: _ClassVar[int]
    COMPATIBILITY_VERSION_FIELD_NUMBER: _ClassVar[int]
    EXTRA_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    SERVER_STEAM_ID_FIELD_NUMBER: _ClassVar[int]
    SERVER_STATE_FIELD_NUMBER: _ClassVar[int]
    UDP_CONNECT_IP_FIELD_NUMBER: _ClassVar[int]
    UDP_CONNECT_PORT_FIELD_NUMBER: _ClassVar[int]
    SDR_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    SERVER_VERSION_FIELD_NUMBER: _ClassVar[int]
    SAFE_TO_ABANDON_FIELD_NUMBER: _ClassVar[int]
    MATCH_PUNISHES_ABANDONS_FIELD_NUMBER: _ClassVar[int]
    GAME_MODE_VERSION_FIELD_NUMBER: _ClassVar[int]
    lobby_id: int
    match_id: int
    match_mode: ECitadelMatchMode
    game_mode: ECitadelGameMode
    compatibility_version: int
    extra_messages: _containers.RepeatedCompositeFieldContainer[_gcsdk_gcmessages_pb2.CExtraMsgBlock]
    server_steam_id: int
    server_state: ELobbyServerState
    udp_connect_ip: int
    udp_connect_port: int
    sdr_address: bytes
    server_version: int
    safe_to_abandon: bool
    match_punishes_abandons: bool
    game_mode_version: int
    def __init__(self, lobby_id: _Optional[int] = ..., match_id: _Optional[int] = ..., match_mode: _Optional[_Union[ECitadelMatchMode, str]] = ..., game_mode: _Optional[_Union[ECitadelGameMode, str]] = ..., compatibility_version: _Optional[int] = ..., extra_messages: _Optional[_Iterable[_Union[_gcsdk_gcmessages_pb2.CExtraMsgBlock, _Mapping]]] = ..., server_steam_id: _Optional[int] = ..., server_state: _Optional[_Union[ELobbyServerState, str]] = ..., udp_connect_ip: _Optional[int] = ..., udp_connect_port: _Optional[int] = ..., sdr_address: _Optional[bytes] = ..., server_version: _Optional[int] = ..., safe_to_abandon: _Optional[bool] = ..., match_punishes_abandons: _Optional[bool] = ..., game_mode_version: _Optional[int] = ...) -> None: ...

class CSOCitadelHideoutLobby(_message.Message):
    __slots__ = ("hideout_lobby_id", "party_id", "server_steam_id", "udp_connect_ip", "udp_connect_port", "sdr_address", "server_version", "compat_version", "members", "active_account_hideout", "extra_messages")
    class Member(_message.Message):
        __slots__ = ("account_id", "hideout_holiday_award_2024", "hideout_holiday_award_2025")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        HIDEOUT_HOLIDAY_AWARD_2024_FIELD_NUMBER: _ClassVar[int]
        HIDEOUT_HOLIDAY_AWARD_2025_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        hideout_holiday_award_2024: bool
        hideout_holiday_award_2025: bool
        def __init__(self, account_id: _Optional[int] = ..., hideout_holiday_award_2024: _Optional[bool] = ..., hideout_holiday_award_2025: _Optional[bool] = ...) -> None: ...
    HIDEOUT_LOBBY_ID_FIELD_NUMBER: _ClassVar[int]
    PARTY_ID_FIELD_NUMBER: _ClassVar[int]
    SERVER_STEAM_ID_FIELD_NUMBER: _ClassVar[int]
    UDP_CONNECT_IP_FIELD_NUMBER: _ClassVar[int]
    UDP_CONNECT_PORT_FIELD_NUMBER: _ClassVar[int]
    SDR_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    SERVER_VERSION_FIELD_NUMBER: _ClassVar[int]
    COMPAT_VERSION_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_ACCOUNT_HIDEOUT_FIELD_NUMBER: _ClassVar[int]
    EXTRA_MESSAGES_FIELD_NUMBER: _ClassVar[int]
    hideout_lobby_id: int
    party_id: int
    server_steam_id: int
    udp_connect_ip: int
    udp_connect_port: int
    sdr_address: bytes
    server_version: int
    compat_version: int
    members: _containers.RepeatedCompositeFieldContainer[CSOCitadelHideoutLobby.Member]
    active_account_hideout: int
    extra_messages: _containers.RepeatedCompositeFieldContainer[_gcsdk_gcmessages_pb2.CExtraMsgBlock]
    def __init__(self, hideout_lobby_id: _Optional[int] = ..., party_id: _Optional[int] = ..., server_steam_id: _Optional[int] = ..., udp_connect_ip: _Optional[int] = ..., udp_connect_port: _Optional[int] = ..., sdr_address: _Optional[bytes] = ..., server_version: _Optional[int] = ..., compat_version: _Optional[int] = ..., members: _Optional[_Iterable[_Union[CSOCitadelHideoutLobby.Member, _Mapping]]] = ..., active_account_hideout: _Optional[int] = ..., extra_messages: _Optional[_Iterable[_Union[_gcsdk_gcmessages_pb2.CExtraMsgBlock, _Mapping]]] = ...) -> None: ...

class CLobbyData_PostMatchSurvey(_message.Message):
    __slots__ = ("surveys",)
    class PlayerSurvey(_message.Message):
        __slots__ = ("account_id", "question_id")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        QUESTION_ID_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        question_id: int
        def __init__(self, account_id: _Optional[int] = ..., question_id: _Optional[int] = ...) -> None: ...
    SURVEYS_FIELD_NUMBER: _ClassVar[int]
    surveys: _containers.RepeatedCompositeFieldContainer[CLobbyData_PostMatchSurvey.PlayerSurvey]
    def __init__(self, surveys: _Optional[_Iterable[_Union[CLobbyData_PostMatchSurvey.PlayerSurvey, _Mapping]]] = ...) -> None: ...

class CMsgHeroSelectionMatchInfo(_message.Message):
    __slots__ = ("hero_selections", "banned_heroes")
    class Hero(_message.Message):
        __slots__ = ("hero_id", "priority")
        HERO_ID_FIELD_NUMBER: _ClassVar[int]
        PRIORITY_FIELD_NUMBER: _ClassVar[int]
        hero_id: int
        priority: int
        def __init__(self, hero_id: _Optional[int] = ..., priority: _Optional[int] = ...) -> None: ...
    HERO_SELECTIONS_FIELD_NUMBER: _ClassVar[int]
    BANNED_HEROES_FIELD_NUMBER: _ClassVar[int]
    hero_selections: _containers.RepeatedCompositeFieldContainer[CMsgHeroSelectionMatchInfo.Hero]
    banned_heroes: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, hero_selections: _Optional[_Iterable[_Union[CMsgHeroSelectionMatchInfo.Hero, _Mapping]]] = ..., banned_heroes: _Optional[_Iterable[int]] = ...) -> None: ...

class CMsgStartFindingMatchInfo(_message.Message):
    __slots__ = ("server_search_key", "server_command_string", "match_mode", "game_mode", "bot_difficulty", "region_mode", "prefer_solo_only", "mm_preference")
    SERVER_SEARCH_KEY_FIELD_NUMBER: _ClassVar[int]
    SERVER_COMMAND_STRING_FIELD_NUMBER: _ClassVar[int]
    MATCH_MODE_FIELD_NUMBER: _ClassVar[int]
    GAME_MODE_FIELD_NUMBER: _ClassVar[int]
    BOT_DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    REGION_MODE_FIELD_NUMBER: _ClassVar[int]
    PREFER_SOLO_ONLY_FIELD_NUMBER: _ClassVar[int]
    MM_PREFERENCE_FIELD_NUMBER: _ClassVar[int]
    server_search_key: str
    server_command_string: str
    match_mode: ECitadelMatchMode
    game_mode: ECitadelGameMode
    bot_difficulty: ECitadelBotDifficulty
    region_mode: ECitadelRegionMode
    prefer_solo_only: bool
    mm_preference: ECitadelMMPreference
    def __init__(self, server_search_key: _Optional[str] = ..., server_command_string: _Optional[str] = ..., match_mode: _Optional[_Union[ECitadelMatchMode, str]] = ..., game_mode: _Optional[_Union[ECitadelGameMode, str]] = ..., bot_difficulty: _Optional[_Union[ECitadelBotDifficulty, str]] = ..., region_mode: _Optional[_Union[ECitadelRegionMode, str]] = ..., prefer_solo_only: _Optional[bool] = ..., mm_preference: _Optional[_Union[ECitadelMMPreference, str]] = ...) -> None: ...

class CMsgAnyToGCReportAsserts(_message.Message):
    __slots__ = ("version", "asserts", "match_id")
    class TrackedAssert(_message.Message):
        __slots__ = ("filename", "line_number", "sample_msg", "sample_stack", "times_fired", "function_name", "condition", "total_times_fired")
        FILENAME_FIELD_NUMBER: _ClassVar[int]
        LINE_NUMBER_FIELD_NUMBER: _ClassVar[int]
        SAMPLE_MSG_FIELD_NUMBER: _ClassVar[int]
        SAMPLE_STACK_FIELD_NUMBER: _ClassVar[int]
        TIMES_FIRED_FIELD_NUMBER: _ClassVar[int]
        FUNCTION_NAME_FIELD_NUMBER: _ClassVar[int]
        CONDITION_FIELD_NUMBER: _ClassVar[int]
        TOTAL_TIMES_FIRED_FIELD_NUMBER: _ClassVar[int]
        filename: str
        line_number: int
        sample_msg: str
        sample_stack: str
        times_fired: int
        function_name: str
        condition: str
        total_times_fired: int
        def __init__(self, filename: _Optional[str] = ..., line_number: _Optional[int] = ..., sample_msg: _Optional[str] = ..., sample_stack: _Optional[str] = ..., times_fired: _Optional[int] = ..., function_name: _Optional[str] = ..., condition: _Optional[str] = ..., total_times_fired: _Optional[int] = ...) -> None: ...
    VERSION_FIELD_NUMBER: _ClassVar[int]
    ASSERTS_FIELD_NUMBER: _ClassVar[int]
    MATCH_ID_FIELD_NUMBER: _ClassVar[int]
    version: int
    asserts: _containers.RepeatedCompositeFieldContainer[CMsgAnyToGCReportAsserts.TrackedAssert]
    match_id: int
    def __init__(self, version: _Optional[int] = ..., asserts: _Optional[_Iterable[_Union[CMsgAnyToGCReportAsserts.TrackedAssert, _Mapping]]] = ..., match_id: _Optional[int] = ...) -> None: ...

class CMsgAnyToGCReportAssertsResponse(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: _Optional[bool] = ...) -> None: ...

class CMsgRegionPingTimesClient(_message.Message):
    __slots__ = ("data_center_codes", "ping_times")
    DATA_CENTER_CODES_FIELD_NUMBER: _ClassVar[int]
    PING_TIMES_FIELD_NUMBER: _ClassVar[int]
    data_center_codes: _containers.RepeatedScalarFieldContainer[int]
    ping_times: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, data_center_codes: _Optional[_Iterable[int]] = ..., ping_times: _Optional[_Iterable[int]] = ...) -> None: ...

class CMsgEquippedItemList(_message.Message):
    __slots__ = ("items",)
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[_base_gcmessages_pb2.CSOEconItem]
    def __init__(self, items: _Optional[_Iterable[_Union[_base_gcmessages_pb2.CSOEconItem, _Mapping]]] = ...) -> None: ...

class CMsgPlayerHeroData(_message.Message):
    __slots__ = ("hero_xp", "hero_equips")
    HERO_XP_FIELD_NUMBER: _ClassVar[int]
    HERO_EQUIPS_FIELD_NUMBER: _ClassVar[int]
    hero_xp: int
    hero_equips: CMsgEquippedItemList
    def __init__(self, hero_xp: _Optional[int] = ..., hero_equips: _Optional[_Union[CMsgEquippedItemList, _Mapping]] = ...) -> None: ...

class CSOCitadelParty(_message.Message):
    __slots__ = ("party_id", "members", "invites", "dev_server_command", "left_members", "join_code", "bot_difficulty", "match_mode", "game_mode", "match_making_start_time", "server_search_key", "is_high_skill_range_party", "chat_mode", "region_mode", "is_private_lobby", "private_lobby_settings", "desires_laning_together", "mm_preference", "hideout_search_key")
    class EMemberRights(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eMemberRights_Admin: _ClassVar[CSOCitadelParty.EMemberRights]
        k_eMemberRights_Creator: _ClassVar[CSOCitadelParty.EMemberRights]
    k_eMemberRights_Admin: CSOCitadelParty.EMemberRights
    k_eMemberRights_Creator: CSOCitadelParty.EMemberRights
    class EPlayerType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_ePlayerType_Player: _ClassVar[CSOCitadelParty.EPlayerType]
        k_ePlayerType_Spectator: _ClassVar[CSOCitadelParty.EPlayerType]
    k_ePlayerType_Player: CSOCitadelParty.EPlayerType
    k_ePlayerType_Spectator: CSOCitadelParty.EPlayerType
    class EChatMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eNone: _ClassVar[CSOCitadelParty.EChatMode]
        k_ePartyChat: _ClassVar[CSOCitadelParty.EChatMode]
        k_eTeamChat: _ClassVar[CSOCitadelParty.EChatMode]
    k_eNone: CSOCitadelParty.EChatMode
    k_ePartyChat: CSOCitadelParty.EChatMode
    k_eTeamChat: CSOCitadelParty.EChatMode
    class PrivateLobbySlot(_message.Message):
        __slots__ = ("slot_id", "player_account_id")
        SLOT_ID_FIELD_NUMBER: _ClassVar[int]
        PLAYER_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        slot_id: int
        player_account_id: int
        def __init__(self, slot_id: _Optional[int] = ..., player_account_id: _Optional[int] = ...) -> None: ...
    class ServerRegion(_message.Message):
        __slots__ = ("region_id",)
        REGION_ID_FIELD_NUMBER: _ClassVar[int]
        region_id: int
        def __init__(self, region_id: _Optional[int] = ...) -> None: ...
    class PrivateLobbySettings(_message.Message):
        __slots__ = ("min_roster_size", "match_slots", "randomize_lanes", "server_region", "is_publicly_visible", "cheats_enabled", "available_regions", "duplicate_heroes_enabled")
        MIN_ROSTER_SIZE_FIELD_NUMBER: _ClassVar[int]
        MATCH_SLOTS_FIELD_NUMBER: _ClassVar[int]
        RANDOMIZE_LANES_FIELD_NUMBER: _ClassVar[int]
        SERVER_REGION_FIELD_NUMBER: _ClassVar[int]
        IS_PUBLICLY_VISIBLE_FIELD_NUMBER: _ClassVar[int]
        CHEATS_ENABLED_FIELD_NUMBER: _ClassVar[int]
        AVAILABLE_REGIONS_FIELD_NUMBER: _ClassVar[int]
        DUPLICATE_HEROES_ENABLED_FIELD_NUMBER: _ClassVar[int]
        min_roster_size: int
        match_slots: _containers.RepeatedCompositeFieldContainer[CSOCitadelParty.PrivateLobbySlot]
        randomize_lanes: bool
        server_region: int
        is_publicly_visible: bool
        cheats_enabled: bool
        available_regions: _containers.RepeatedCompositeFieldContainer[CSOCitadelParty.ServerRegion]
        duplicate_heroes_enabled: bool
        def __init__(self, min_roster_size: _Optional[int] = ..., match_slots: _Optional[_Iterable[_Union[CSOCitadelParty.PrivateLobbySlot, _Mapping]]] = ..., randomize_lanes: _Optional[bool] = ..., server_region: _Optional[int] = ..., is_publicly_visible: _Optional[bool] = ..., cheats_enabled: _Optional[bool] = ..., available_regions: _Optional[_Iterable[_Union[CSOCitadelParty.ServerRegion, _Mapping]]] = ..., duplicate_heroes_enabled: _Optional[bool] = ...) -> None: ...
    class Member(_message.Message):
        __slots__ = ("account_id", "persona_name", "rights_flags", "is_ready", "player_type", "compatibility_version", "platform", "team", "hero_roster", "permissions", "new_player_progress", "owned_heroes", "low_priority_games_remaining")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        PERSONA_NAME_FIELD_NUMBER: _ClassVar[int]
        RIGHTS_FLAGS_FIELD_NUMBER: _ClassVar[int]
        IS_READY_FIELD_NUMBER: _ClassVar[int]
        PLAYER_TYPE_FIELD_NUMBER: _ClassVar[int]
        COMPATIBILITY_VERSION_FIELD_NUMBER: _ClassVar[int]
        PLATFORM_FIELD_NUMBER: _ClassVar[int]
        TEAM_FIELD_NUMBER: _ClassVar[int]
        HERO_ROSTER_FIELD_NUMBER: _ClassVar[int]
        PERMISSIONS_FIELD_NUMBER: _ClassVar[int]
        NEW_PLAYER_PROGRESS_FIELD_NUMBER: _ClassVar[int]
        OWNED_HEROES_FIELD_NUMBER: _ClassVar[int]
        LOW_PRIORITY_GAMES_REMAINING_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        persona_name: str
        rights_flags: int
        is_ready: bool
        player_type: CSOCitadelParty.EPlayerType
        compatibility_version: int
        platform: _steammessages_pb2.EGCPlatform
        team: int
        hero_roster: CMsgHeroSelectionMatchInfo
        permissions: int
        new_player_progress: int
        owned_heroes: _containers.RepeatedScalarFieldContainer[int]
        low_priority_games_remaining: int
        def __init__(self, account_id: _Optional[int] = ..., persona_name: _Optional[str] = ..., rights_flags: _Optional[int] = ..., is_ready: _Optional[bool] = ..., player_type: _Optional[_Union[CSOCitadelParty.EPlayerType, str]] = ..., compatibility_version: _Optional[int] = ..., platform: _Optional[_Union[_steammessages_pb2.EGCPlatform, str]] = ..., team: _Optional[int] = ..., hero_roster: _Optional[_Union[CMsgHeroSelectionMatchInfo, _Mapping]] = ..., permissions: _Optional[int] = ..., new_player_progress: _Optional[int] = ..., owned_heroes: _Optional[_Iterable[int]] = ..., low_priority_games_remaining: _Optional[int] = ...) -> None: ...
    class LeftMember(_message.Message):
        __slots__ = ("account_id", "rights_flags", "player_type")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        RIGHTS_FLAGS_FIELD_NUMBER: _ClassVar[int]
        PLAYER_TYPE_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        rights_flags: int
        player_type: CSOCitadelParty.EPlayerType
        def __init__(self, account_id: _Optional[int] = ..., rights_flags: _Optional[int] = ..., player_type: _Optional[_Union[CSOCitadelParty.EPlayerType, str]] = ...) -> None: ...
    class Invite(_message.Message):
        __slots__ = ("account_id", "persona_name", "invited_by")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        PERSONA_NAME_FIELD_NUMBER: _ClassVar[int]
        INVITED_BY_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        persona_name: str
        invited_by: int
        def __init__(self, account_id: _Optional[int] = ..., persona_name: _Optional[str] = ..., invited_by: _Optional[int] = ...) -> None: ...
    PARTY_ID_FIELD_NUMBER: _ClassVar[int]
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    INVITES_FIELD_NUMBER: _ClassVar[int]
    DEV_SERVER_COMMAND_FIELD_NUMBER: _ClassVar[int]
    LEFT_MEMBERS_FIELD_NUMBER: _ClassVar[int]
    JOIN_CODE_FIELD_NUMBER: _ClassVar[int]
    BOT_DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    MATCH_MODE_FIELD_NUMBER: _ClassVar[int]
    GAME_MODE_FIELD_NUMBER: _ClassVar[int]
    MATCH_MAKING_START_TIME_FIELD_NUMBER: _ClassVar[int]
    SERVER_SEARCH_KEY_FIELD_NUMBER: _ClassVar[int]
    IS_HIGH_SKILL_RANGE_PARTY_FIELD_NUMBER: _ClassVar[int]
    CHAT_MODE_FIELD_NUMBER: _ClassVar[int]
    REGION_MODE_FIELD_NUMBER: _ClassVar[int]
    IS_PRIVATE_LOBBY_FIELD_NUMBER: _ClassVar[int]
    PRIVATE_LOBBY_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    DESIRES_LANING_TOGETHER_FIELD_NUMBER: _ClassVar[int]
    MM_PREFERENCE_FIELD_NUMBER: _ClassVar[int]
    HIDEOUT_SEARCH_KEY_FIELD_NUMBER: _ClassVar[int]
    party_id: int
    members: _containers.RepeatedCompositeFieldContainer[CSOCitadelParty.Member]
    invites: _containers.RepeatedCompositeFieldContainer[CSOCitadelParty.Invite]
    dev_server_command: str
    left_members: _containers.RepeatedCompositeFieldContainer[CSOCitadelParty.LeftMember]
    join_code: int
    bot_difficulty: ECitadelBotDifficulty
    match_mode: ECitadelMatchMode
    game_mode: ECitadelGameMode
    match_making_start_time: int
    server_search_key: str
    is_high_skill_range_party: bool
    chat_mode: CSOCitadelParty.EChatMode
    region_mode: ECitadelRegionMode
    is_private_lobby: bool
    private_lobby_settings: CSOCitadelParty.PrivateLobbySettings
    desires_laning_together: bool
    mm_preference: ECitadelMMPreference
    hideout_search_key: str
    def __init__(self, party_id: _Optional[int] = ..., members: _Optional[_Iterable[_Union[CSOCitadelParty.Member, _Mapping]]] = ..., invites: _Optional[_Iterable[_Union[CSOCitadelParty.Invite, _Mapping]]] = ..., dev_server_command: _Optional[str] = ..., left_members: _Optional[_Iterable[_Union[CSOCitadelParty.LeftMember, _Mapping]]] = ..., join_code: _Optional[int] = ..., bot_difficulty: _Optional[_Union[ECitadelBotDifficulty, str]] = ..., match_mode: _Optional[_Union[ECitadelMatchMode, str]] = ..., game_mode: _Optional[_Union[ECitadelGameMode, str]] = ..., match_making_start_time: _Optional[int] = ..., server_search_key: _Optional[str] = ..., is_high_skill_range_party: _Optional[bool] = ..., chat_mode: _Optional[_Union[CSOCitadelParty.EChatMode, str]] = ..., region_mode: _Optional[_Union[ECitadelRegionMode, str]] = ..., is_private_lobby: _Optional[bool] = ..., private_lobby_settings: _Optional[_Union[CSOCitadelParty.PrivateLobbySettings, _Mapping]] = ..., desires_laning_together: _Optional[bool] = ..., mm_preference: _Optional[_Union[ECitadelMMPreference, str]] = ..., hideout_search_key: _Optional[str] = ...) -> None: ...

class CMsgMatchPlayerPathsData(_message.Message):
    __slots__ = ("version", "interval_s", "x_resolution", "y_resolution", "paths")
    class ECombatType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eCombatType_Out: _ClassVar[CMsgMatchPlayerPathsData.ECombatType]
        k_eCombatType_Player: _ClassVar[CMsgMatchPlayerPathsData.ECombatType]
        k_eCombatType_EnemyNPC: _ClassVar[CMsgMatchPlayerPathsData.ECombatType]
        k_eCombatType_Neutral: _ClassVar[CMsgMatchPlayerPathsData.ECombatType]
    k_eCombatType_Out: CMsgMatchPlayerPathsData.ECombatType
    k_eCombatType_Player: CMsgMatchPlayerPathsData.ECombatType
    k_eCombatType_EnemyNPC: CMsgMatchPlayerPathsData.ECombatType
    k_eCombatType_Neutral: CMsgMatchPlayerPathsData.ECombatType
    class EMoveType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eMoveType_Normal: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_Ability: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_AbilityDebuff: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_GroundDash: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_Slide: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_RopeClimbing: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_Ziplining: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_InAir: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
        k_eMoveType_AirDash: _ClassVar[CMsgMatchPlayerPathsData.EMoveType]
    k_eMoveType_Normal: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_Ability: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_AbilityDebuff: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_GroundDash: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_Slide: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_RopeClimbing: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_Ziplining: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_InAir: CMsgMatchPlayerPathsData.EMoveType
    k_eMoveType_AirDash: CMsgMatchPlayerPathsData.EMoveType
    class Path(_message.Message):
        __slots__ = ("player_slot", "x_min", "y_min", "x_max", "y_max", "x_pos", "y_pos", "health", "combat_type", "move_type")
        PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        X_MIN_FIELD_NUMBER: _ClassVar[int]
        Y_MIN_FIELD_NUMBER: _ClassVar[int]
        X_MAX_FIELD_NUMBER: _ClassVar[int]
        Y_MAX_FIELD_NUMBER: _ClassVar[int]
        X_POS_FIELD_NUMBER: _ClassVar[int]
        Y_POS_FIELD_NUMBER: _ClassVar[int]
        HEALTH_FIELD_NUMBER: _ClassVar[int]
        COMBAT_TYPE_FIELD_NUMBER: _ClassVar[int]
        MOVE_TYPE_FIELD_NUMBER: _ClassVar[int]
        player_slot: int
        x_min: float
        y_min: float
        x_max: float
        y_max: float
        x_pos: _containers.RepeatedScalarFieldContainer[int]
        y_pos: _containers.RepeatedScalarFieldContainer[int]
        health: _containers.RepeatedScalarFieldContainer[int]
        combat_type: _containers.RepeatedScalarFieldContainer[CMsgMatchPlayerPathsData.ECombatType]
        move_type: _containers.RepeatedScalarFieldContainer[CMsgMatchPlayerPathsData.EMoveType]
        def __init__(self, player_slot: _Optional[int] = ..., x_min: _Optional[float] = ..., y_min: _Optional[float] = ..., x_max: _Optional[float] = ..., y_max: _Optional[float] = ..., x_pos: _Optional[_Iterable[int]] = ..., y_pos: _Optional[_Iterable[int]] = ..., health: _Optional[_Iterable[int]] = ..., combat_type: _Optional[_Iterable[_Union[CMsgMatchPlayerPathsData.ECombatType, str]]] = ..., move_type: _Optional[_Iterable[_Union[CMsgMatchPlayerPathsData.EMoveType, str]]] = ...) -> None: ...
    VERSION_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_S_FIELD_NUMBER: _ClassVar[int]
    X_RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    Y_RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    PATHS_FIELD_NUMBER: _ClassVar[int]
    version: int
    interval_s: float
    x_resolution: int
    y_resolution: int
    paths: _containers.RepeatedCompositeFieldContainer[CMsgMatchPlayerPathsData.Path]
    def __init__(self, version: _Optional[int] = ..., interval_s: _Optional[float] = ..., x_resolution: _Optional[int] = ..., y_resolution: _Optional[int] = ..., paths: _Optional[_Iterable[_Union[CMsgMatchPlayerPathsData.Path, _Mapping]]] = ...) -> None: ...

class CMsgMatchPlayerDamageMatrix(_message.Message):
    __slots__ = ("damage_dealers", "sample_time_s", "source_details")
    class EStatType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eType_Damage: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
        k_eType_Healing: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
        k_eType_HealPrevented: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
        k_eType_Mitigated: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
        k_eType_LethalDamage: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
        k_eType_Regen: _ClassVar[CMsgMatchPlayerDamageMatrix.EStatType]
    k_eType_Damage: CMsgMatchPlayerDamageMatrix.EStatType
    k_eType_Healing: CMsgMatchPlayerDamageMatrix.EStatType
    k_eType_HealPrevented: CMsgMatchPlayerDamageMatrix.EStatType
    k_eType_Mitigated: CMsgMatchPlayerDamageMatrix.EStatType
    k_eType_LethalDamage: CMsgMatchPlayerDamageMatrix.EStatType
    k_eType_Regen: CMsgMatchPlayerDamageMatrix.EStatType
    class DamageToPlayer(_message.Message):
        __slots__ = ("target_player_slot", "damage")
        TARGET_PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_FIELD_NUMBER: _ClassVar[int]
        target_player_slot: int
        damage: _containers.RepeatedScalarFieldContainer[int]
        def __init__(self, target_player_slot: _Optional[int] = ..., damage: _Optional[_Iterable[int]] = ...) -> None: ...
    class DamageSource(_message.Message):
        __slots__ = ("damage_to_players", "source_details_index")
        DAMAGE_TO_PLAYERS_FIELD_NUMBER: _ClassVar[int]
        SOURCE_DETAILS_INDEX_FIELD_NUMBER: _ClassVar[int]
        damage_to_players: _containers.RepeatedCompositeFieldContainer[CMsgMatchPlayerDamageMatrix.DamageToPlayer]
        source_details_index: int
        def __init__(self, damage_to_players: _Optional[_Iterable[_Union[CMsgMatchPlayerDamageMatrix.DamageToPlayer, _Mapping]]] = ..., source_details_index: _Optional[int] = ...) -> None: ...
    class DamageDealer(_message.Message):
        __slots__ = ("dealer_player_slot", "damage_sources")
        DEALER_PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_SOURCES_FIELD_NUMBER: _ClassVar[int]
        dealer_player_slot: int
        damage_sources: _containers.RepeatedCompositeFieldContainer[CMsgMatchPlayerDamageMatrix.DamageSource]
        def __init__(self, dealer_player_slot: _Optional[int] = ..., damage_sources: _Optional[_Iterable[_Union[CMsgMatchPlayerDamageMatrix.DamageSource, _Mapping]]] = ...) -> None: ...
    class SourceDetails(_message.Message):
        __slots__ = ("stat_type", "source_name")
        STAT_TYPE_FIELD_NUMBER: _ClassVar[int]
        SOURCE_NAME_FIELD_NUMBER: _ClassVar[int]
        stat_type: _containers.RepeatedScalarFieldContainer[CMsgMatchPlayerDamageMatrix.EStatType]
        source_name: _containers.RepeatedScalarFieldContainer[str]
        def __init__(self, stat_type: _Optional[_Iterable[_Union[CMsgMatchPlayerDamageMatrix.EStatType, str]]] = ..., source_name: _Optional[_Iterable[str]] = ...) -> None: ...
    DAMAGE_DEALERS_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_TIME_S_FIELD_NUMBER: _ClassVar[int]
    SOURCE_DETAILS_FIELD_NUMBER: _ClassVar[int]
    damage_dealers: _containers.RepeatedCompositeFieldContainer[CMsgMatchPlayerDamageMatrix.DamageDealer]
    sample_time_s: _containers.RepeatedScalarFieldContainer[int]
    source_details: CMsgMatchPlayerDamageMatrix.SourceDetails
    def __init__(self, damage_dealers: _Optional[_Iterable[_Union[CMsgMatchPlayerDamageMatrix.DamageDealer, _Mapping]]] = ..., sample_time_s: _Optional[_Iterable[int]] = ..., source_details: _Optional[_Union[CMsgMatchPlayerDamageMatrix.SourceDetails, _Mapping]] = ...) -> None: ...

class CMsgMatchMetaDataContents(_message.Message):
    __slots__ = ("match_info",)
    class EMatchOutcome(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_eOutcome_TeamWin: _ClassVar[CMsgMatchMetaDataContents.EMatchOutcome]
        k_eOutcome_Error: _ClassVar[CMsgMatchMetaDataContents.EMatchOutcome]
        k_eOutcome_MatchDraw: _ClassVar[CMsgMatchMetaDataContents.EMatchOutcome]
    k_eOutcome_TeamWin: CMsgMatchMetaDataContents.EMatchOutcome
    k_eOutcome_Error: CMsgMatchMetaDataContents.EMatchOutcome
    k_eOutcome_MatchDraw: CMsgMatchMetaDataContents.EMatchOutcome
    class EGoldSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        k_ePlayers: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eLaneCreeps: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eNeutrals: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eBosses: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eTreasure: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eAssists: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eDenies: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eTeamBonus: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eAbilityAssassinate: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eItemTrophyCollector: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eItemCultistSacrifice: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eBreakable: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
        k_eItemGooseEgg: _ClassVar[CMsgMatchMetaDataContents.EGoldSource]
    k_ePlayers: CMsgMatchMetaDataContents.EGoldSource
    k_eLaneCreeps: CMsgMatchMetaDataContents.EGoldSource
    k_eNeutrals: CMsgMatchMetaDataContents.EGoldSource
    k_eBosses: CMsgMatchMetaDataContents.EGoldSource
    k_eTreasure: CMsgMatchMetaDataContents.EGoldSource
    k_eAssists: CMsgMatchMetaDataContents.EGoldSource
    k_eDenies: CMsgMatchMetaDataContents.EGoldSource
    k_eTeamBonus: CMsgMatchMetaDataContents.EGoldSource
    k_eAbilityAssassinate: CMsgMatchMetaDataContents.EGoldSource
    k_eItemTrophyCollector: CMsgMatchMetaDataContents.EGoldSource
    k_eItemCultistSacrifice: CMsgMatchMetaDataContents.EGoldSource
    k_eBreakable: CMsgMatchMetaDataContents.EGoldSource
    k_eItemGooseEgg: CMsgMatchMetaDataContents.EGoldSource
    class Position(_message.Message):
        __slots__ = ("x", "y", "z")
        X_FIELD_NUMBER: _ClassVar[int]
        Y_FIELD_NUMBER: _ClassVar[int]
        Z_FIELD_NUMBER: _ClassVar[int]
        x: float
        y: float
        z: float
        def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...
    class Deaths(_message.Message):
        __slots__ = ("game_time_s", "time_to_kill_s", "killer_player_slot", "death_pos", "killer_pos", "death_duration_s")
        GAME_TIME_S_FIELD_NUMBER: _ClassVar[int]
        TIME_TO_KILL_S_FIELD_NUMBER: _ClassVar[int]
        KILLER_PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        DEATH_POS_FIELD_NUMBER: _ClassVar[int]
        KILLER_POS_FIELD_NUMBER: _ClassVar[int]
        DEATH_DURATION_S_FIELD_NUMBER: _ClassVar[int]
        game_time_s: int
        time_to_kill_s: float
        killer_player_slot: int
        death_pos: CMsgMatchMetaDataContents.Position
        killer_pos: CMsgMatchMetaDataContents.Position
        death_duration_s: int
        def __init__(self, game_time_s: _Optional[int] = ..., time_to_kill_s: _Optional[float] = ..., killer_player_slot: _Optional[int] = ..., death_pos: _Optional[_Union[CMsgMatchMetaDataContents.Position, _Mapping]] = ..., killer_pos: _Optional[_Union[CMsgMatchMetaDataContents.Position, _Mapping]] = ..., death_duration_s: _Optional[int] = ...) -> None: ...
    class Items(_message.Message):
        __slots__ = ("game_time_s", "item_id", "upgrade_id", "sold_time_s", "flags", "imbued_ability_id", "upgrade_info")
        GAME_TIME_S_FIELD_NUMBER: _ClassVar[int]
        ITEM_ID_FIELD_NUMBER: _ClassVar[int]
        UPGRADE_ID_FIELD_NUMBER: _ClassVar[int]
        SOLD_TIME_S_FIELD_NUMBER: _ClassVar[int]
        FLAGS_FIELD_NUMBER: _ClassVar[int]
        IMBUED_ABILITY_ID_FIELD_NUMBER: _ClassVar[int]
        UPGRADE_INFO_FIELD_NUMBER: _ClassVar[int]
        game_time_s: int
        item_id: int
        upgrade_id: int
        sold_time_s: int
        flags: int
        imbued_ability_id: int
        upgrade_info: int
        def __init__(self, game_time_s: _Optional[int] = ..., item_id: _Optional[int] = ..., upgrade_id: _Optional[int] = ..., sold_time_s: _Optional[int] = ..., flags: _Optional[int] = ..., imbued_ability_id: _Optional[int] = ..., upgrade_info: _Optional[int] = ...) -> None: ...
    class Ping(_message.Message):
        __slots__ = ("ping_type", "ping_data", "game_time_s")
        PING_TYPE_FIELD_NUMBER: _ClassVar[int]
        PING_DATA_FIELD_NUMBER: _ClassVar[int]
        GAME_TIME_S_FIELD_NUMBER: _ClassVar[int]
        ping_type: int
        ping_data: int
        game_time_s: int
        def __init__(self, ping_type: _Optional[int] = ..., ping_data: _Optional[int] = ..., game_time_s: _Optional[int] = ...) -> None: ...
    class GoldSource(_message.Message):
        __slots__ = ("source", "kills", "damage", "gold", "gold_orbs")
        SOURCE_FIELD_NUMBER: _ClassVar[int]
        KILLS_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_FIELD_NUMBER: _ClassVar[int]
        GOLD_FIELD_NUMBER: _ClassVar[int]
        GOLD_ORBS_FIELD_NUMBER: _ClassVar[int]
        source: CMsgMatchMetaDataContents.EGoldSource
        kills: int
        damage: int
        gold: int
        gold_orbs: int
        def __init__(self, source: _Optional[_Union[CMsgMatchMetaDataContents.EGoldSource, str]] = ..., kills: _Optional[int] = ..., damage: _Optional[int] = ..., gold: _Optional[int] = ..., gold_orbs: _Optional[int] = ...) -> None: ...
    class CustomUserStatInfo(_message.Message):
        __slots__ = ("name", "id")
        NAME_FIELD_NUMBER: _ClassVar[int]
        ID_FIELD_NUMBER: _ClassVar[int]
        name: str
        id: int
        def __init__(self, name: _Optional[str] = ..., id: _Optional[int] = ...) -> None: ...
    class CustomUserStat(_message.Message):
        __slots__ = ("value", "id")
        VALUE_FIELD_NUMBER: _ClassVar[int]
        ID_FIELD_NUMBER: _ClassVar[int]
        value: int
        id: int
        def __init__(self, value: _Optional[int] = ..., id: _Optional[int] = ...) -> None: ...
    class PowerUpBuff(_message.Message):
        __slots__ = ("type", "value", "is_permanent")
        TYPE_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        IS_PERMANENT_FIELD_NUMBER: _ClassVar[int]
        type: str
        value: int
        is_permanent: bool
        def __init__(self, type: _Optional[str] = ..., value: _Optional[int] = ..., is_permanent: _Optional[bool] = ...) -> None: ...
    class PlayerStats(_message.Message):
        __slots__ = ("time_stamp_s", "net_worth", "gold_player", "gold_player_orbs", "gold_lane_creep_orbs", "gold_neutral_creep_orbs", "gold_boss", "gold_boss_orb", "gold_treasure", "gold_denied", "gold_death_loss", "gold_lane_creep", "gold_neutral_creep", "kills", "deaths", "assists", "creep_kills", "neutral_kills", "possible_creeps", "creep_damage", "player_damage", "neutral_damage", "boss_damage", "denies", "player_healing", "ability_points", "self_healing", "player_damage_taken", "max_health", "weapon_power", "tech_power", "shots_hit", "shots_missed", "damage_absorbed", "absorption_provided", "hero_bullets_hit", "hero_bullets_hit_crit", "heal_prevented", "heal_lost", "gold_sources", "custom_user_stats", "damage_mitigated", "level", "player_barriering", "teammate_healing", "teammate_barriering", "self_damage", "bullet_kills", "melee_kills", "ability_kills", "headshot_kills")
        TIME_STAMP_S_FIELD_NUMBER: _ClassVar[int]
        NET_WORTH_FIELD_NUMBER: _ClassVar[int]
        GOLD_PLAYER_FIELD_NUMBER: _ClassVar[int]
        GOLD_PLAYER_ORBS_FIELD_NUMBER: _ClassVar[int]
        GOLD_LANE_CREEP_ORBS_FIELD_NUMBER: _ClassVar[int]
        GOLD_NEUTRAL_CREEP_ORBS_FIELD_NUMBER: _ClassVar[int]
        GOLD_BOSS_FIELD_NUMBER: _ClassVar[int]
        GOLD_BOSS_ORB_FIELD_NUMBER: _ClassVar[int]
        GOLD_TREASURE_FIELD_NUMBER: _ClassVar[int]
        GOLD_DENIED_FIELD_NUMBER: _ClassVar[int]
        GOLD_DEATH_LOSS_FIELD_NUMBER: _ClassVar[int]
        GOLD_LANE_CREEP_FIELD_NUMBER: _ClassVar[int]
        GOLD_NEUTRAL_CREEP_FIELD_NUMBER: _ClassVar[int]
        KILLS_FIELD_NUMBER: _ClassVar[int]
        DEATHS_FIELD_NUMBER: _ClassVar[int]
        ASSISTS_FIELD_NUMBER: _ClassVar[int]
        CREEP_KILLS_FIELD_NUMBER: _ClassVar[int]
        NEUTRAL_KILLS_FIELD_NUMBER: _ClassVar[int]
        POSSIBLE_CREEPS_FIELD_NUMBER: _ClassVar[int]
        CREEP_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        PLAYER_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        NEUTRAL_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        BOSS_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        DENIES_FIELD_NUMBER: _ClassVar[int]
        PLAYER_HEALING_FIELD_NUMBER: _ClassVar[int]
        ABILITY_POINTS_FIELD_NUMBER: _ClassVar[int]
        SELF_HEALING_FIELD_NUMBER: _ClassVar[int]
        PLAYER_DAMAGE_TAKEN_FIELD_NUMBER: _ClassVar[int]
        MAX_HEALTH_FIELD_NUMBER: _ClassVar[int]
        WEAPON_POWER_FIELD_NUMBER: _ClassVar[int]
        TECH_POWER_FIELD_NUMBER: _ClassVar[int]
        SHOTS_HIT_FIELD_NUMBER: _ClassVar[int]
        SHOTS_MISSED_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_ABSORBED_FIELD_NUMBER: _ClassVar[int]
        ABSORPTION_PROVIDED_FIELD_NUMBER: _ClassVar[int]
        HERO_BULLETS_HIT_FIELD_NUMBER: _ClassVar[int]
        HERO_BULLETS_HIT_CRIT_FIELD_NUMBER: _ClassVar[int]
        HEAL_PREVENTED_FIELD_NUMBER: _ClassVar[int]
        HEAL_LOST_FIELD_NUMBER: _ClassVar[int]
        GOLD_SOURCES_FIELD_NUMBER: _ClassVar[int]
        CUSTOM_USER_STATS_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_MITIGATED_FIELD_NUMBER: _ClassVar[int]
        LEVEL_FIELD_NUMBER: _ClassVar[int]
        PLAYER_BARRIERING_FIELD_NUMBER: _ClassVar[int]
        TEAMMATE_HEALING_FIELD_NUMBER: _ClassVar[int]
        TEAMMATE_BARRIERING_FIELD_NUMBER: _ClassVar[int]
        SELF_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        BULLET_KILLS_FIELD_NUMBER: _ClassVar[int]
        MELEE_KILLS_FIELD_NUMBER: _ClassVar[int]
        ABILITY_KILLS_FIELD_NUMBER: _ClassVar[int]
        HEADSHOT_KILLS_FIELD_NUMBER: _ClassVar[int]
        time_stamp_s: int
        net_worth: int
        gold_player: int
        gold_player_orbs: int
        gold_lane_creep_orbs: int
        gold_neutral_creep_orbs: int
        gold_boss: int
        gold_boss_orb: int
        gold_treasure: int
        gold_denied: int
        gold_death_loss: int
        gold_lane_creep: int
        gold_neutral_creep: int
        kills: int
        deaths: int
        assists: int
        creep_kills: int
        neutral_kills: int
        possible_creeps: int
        creep_damage: int
        player_damage: int
        neutral_damage: int
        boss_damage: int
        denies: int
        player_healing: int
        ability_points: int
        self_healing: int
        player_damage_taken: int
        max_health: int
        weapon_power: int
        tech_power: int
        shots_hit: int
        shots_missed: int
        damage_absorbed: int
        absorption_provided: int
        hero_bullets_hit: int
        hero_bullets_hit_crit: int
        heal_prevented: int
        heal_lost: int
        gold_sources: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.GoldSource]
        custom_user_stats: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.CustomUserStat]
        damage_mitigated: int
        level: int
        player_barriering: int
        teammate_healing: int
        teammate_barriering: int
        self_damage: int
        bullet_kills: int
        melee_kills: int
        ability_kills: int
        headshot_kills: int
        def __init__(self, time_stamp_s: _Optional[int] = ..., net_worth: _Optional[int] = ..., gold_player: _Optional[int] = ..., gold_player_orbs: _Optional[int] = ..., gold_lane_creep_orbs: _Optional[int] = ..., gold_neutral_creep_orbs: _Optional[int] = ..., gold_boss: _Optional[int] = ..., gold_boss_orb: _Optional[int] = ..., gold_treasure: _Optional[int] = ..., gold_denied: _Optional[int] = ..., gold_death_loss: _Optional[int] = ..., gold_lane_creep: _Optional[int] = ..., gold_neutral_creep: _Optional[int] = ..., kills: _Optional[int] = ..., deaths: _Optional[int] = ..., assists: _Optional[int] = ..., creep_kills: _Optional[int] = ..., neutral_kills: _Optional[int] = ..., possible_creeps: _Optional[int] = ..., creep_damage: _Optional[int] = ..., player_damage: _Optional[int] = ..., neutral_damage: _Optional[int] = ..., boss_damage: _Optional[int] = ..., denies: _Optional[int] = ..., player_healing: _Optional[int] = ..., ability_points: _Optional[int] = ..., self_healing: _Optional[int] = ..., player_damage_taken: _Optional[int] = ..., max_health: _Optional[int] = ..., weapon_power: _Optional[int] = ..., tech_power: _Optional[int] = ..., shots_hit: _Optional[int] = ..., shots_missed: _Optional[int] = ..., damage_absorbed: _Optional[int] = ..., absorption_provided: _Optional[int] = ..., hero_bullets_hit: _Optional[int] = ..., hero_bullets_hit_crit: _Optional[int] = ..., heal_prevented: _Optional[int] = ..., heal_lost: _Optional[int] = ..., gold_sources: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.GoldSource, _Mapping]]] = ..., custom_user_stats: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.CustomUserStat, _Mapping]]] = ..., damage_mitigated: _Optional[int] = ..., level: _Optional[int] = ..., player_barriering: _Optional[int] = ..., teammate_healing: _Optional[int] = ..., teammate_barriering: _Optional[int] = ..., self_damage: _Optional[int] = ..., bullet_kills: _Optional[int] = ..., melee_kills: _Optional[int] = ..., ability_kills: _Optional[int] = ..., headshot_kills: _Optional[int] = ...) -> None: ...
    class AbilityStat(_message.Message):
        __slots__ = ("ability_id", "ability_value")
        ABILITY_ID_FIELD_NUMBER: _ClassVar[int]
        ABILITY_VALUE_FIELD_NUMBER: _ClassVar[int]
        ability_id: int
        ability_value: int
        def __init__(self, ability_id: _Optional[int] = ..., ability_value: _Optional[int] = ...) -> None: ...
    class BookReward(_message.Message):
        __slots__ = ("book_id", "xp_amount", "starting_xp")
        BOOK_ID_FIELD_NUMBER: _ClassVar[int]
        XP_AMOUNT_FIELD_NUMBER: _ClassVar[int]
        STARTING_XP_FIELD_NUMBER: _ClassVar[int]
        book_id: int
        xp_amount: int
        starting_xp: int
        def __init__(self, book_id: _Optional[int] = ..., xp_amount: _Optional[int] = ..., starting_xp: _Optional[int] = ...) -> None: ...
    class PlayerAccolade(_message.Message):
        __slots__ = ("accolade_id", "accolade_stat_value", "accolade_threshold_achieved")
        ACCOLADE_ID_FIELD_NUMBER: _ClassVar[int]
        ACCOLADE_STAT_VALUE_FIELD_NUMBER: _ClassVar[int]
        ACCOLADE_THRESHOLD_ACHIEVED_FIELD_NUMBER: _ClassVar[int]
        accolade_id: int
        accolade_stat_value: int
        accolade_threshold_achieved: int
        def __init__(self, accolade_id: _Optional[int] = ..., accolade_stat_value: _Optional[int] = ..., accolade_threshold_achieved: _Optional[int] = ...) -> None: ...
    class Players(_message.Message):
        __slots__ = ("account_id", "player_slot", "death_details", "items", "stats", "team", "kills", "deaths", "assists", "net_worth", "hero_id", "last_hits", "denies", "ability_points", "assigned_lane", "level", "pings", "ability_stats", "stats_type_stat", "book_rewards", "abandon_match_time_s", "hero_data", "rewards_eligible", "player_tracked_stats", "accolades", "mvp_rank", "earned_holiday_award_2025", "power_up_buffs")
        ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
        PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        DEATH_DETAILS_FIELD_NUMBER: _ClassVar[int]
        ITEMS_FIELD_NUMBER: _ClassVar[int]
        STATS_FIELD_NUMBER: _ClassVar[int]
        TEAM_FIELD_NUMBER: _ClassVar[int]
        KILLS_FIELD_NUMBER: _ClassVar[int]
        DEATHS_FIELD_NUMBER: _ClassVar[int]
        ASSISTS_FIELD_NUMBER: _ClassVar[int]
        NET_WORTH_FIELD_NUMBER: _ClassVar[int]
        HERO_ID_FIELD_NUMBER: _ClassVar[int]
        LAST_HITS_FIELD_NUMBER: _ClassVar[int]
        DENIES_FIELD_NUMBER: _ClassVar[int]
        ABILITY_POINTS_FIELD_NUMBER: _ClassVar[int]
        ASSIGNED_LANE_FIELD_NUMBER: _ClassVar[int]
        LEVEL_FIELD_NUMBER: _ClassVar[int]
        PINGS_FIELD_NUMBER: _ClassVar[int]
        ABILITY_STATS_FIELD_NUMBER: _ClassVar[int]
        STATS_TYPE_STAT_FIELD_NUMBER: _ClassVar[int]
        BOOK_REWARDS_FIELD_NUMBER: _ClassVar[int]
        ABANDON_MATCH_TIME_S_FIELD_NUMBER: _ClassVar[int]
        HERO_DATA_FIELD_NUMBER: _ClassVar[int]
        REWARDS_ELIGIBLE_FIELD_NUMBER: _ClassVar[int]
        PLAYER_TRACKED_STATS_FIELD_NUMBER: _ClassVar[int]
        ACCOLADES_FIELD_NUMBER: _ClassVar[int]
        MVP_RANK_FIELD_NUMBER: _ClassVar[int]
        EARNED_HOLIDAY_AWARD_2025_FIELD_NUMBER: _ClassVar[int]
        POWER_UP_BUFFS_FIELD_NUMBER: _ClassVar[int]
        account_id: int
        player_slot: int
        death_details: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Deaths]
        items: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Items]
        stats: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.PlayerStats]
        team: ECitadelLobbyTeam
        kills: int
        deaths: int
        assists: int
        net_worth: int
        hero_id: int
        last_hits: int
        denies: int
        ability_points: int
        assigned_lane: int
        level: int
        pings: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Ping]
        ability_stats: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.AbilityStat]
        stats_type_stat: _containers.RepeatedScalarFieldContainer[float]
        book_rewards: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.BookReward]
        abandon_match_time_s: int
        hero_data: CMsgPlayerHeroData
        rewards_eligible: bool
        player_tracked_stats: _containers.RepeatedCompositeFieldContainer[CMsgTrackedStat]
        accolades: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.PlayerAccolade]
        mvp_rank: int
        earned_holiday_award_2025: bool
        power_up_buffs: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.PowerUpBuff]
        def __init__(self, account_id: _Optional[int] = ..., player_slot: _Optional[int] = ..., death_details: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Deaths, _Mapping]]] = ..., items: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Items, _Mapping]]] = ..., stats: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.PlayerStats, _Mapping]]] = ..., team: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., kills: _Optional[int] = ..., deaths: _Optional[int] = ..., assists: _Optional[int] = ..., net_worth: _Optional[int] = ..., hero_id: _Optional[int] = ..., last_hits: _Optional[int] = ..., denies: _Optional[int] = ..., ability_points: _Optional[int] = ..., assigned_lane: _Optional[int] = ..., level: _Optional[int] = ..., pings: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Ping, _Mapping]]] = ..., ability_stats: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.AbilityStat, _Mapping]]] = ..., stats_type_stat: _Optional[_Iterable[float]] = ..., book_rewards: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.BookReward, _Mapping]]] = ..., abandon_match_time_s: _Optional[int] = ..., hero_data: _Optional[_Union[CMsgPlayerHeroData, _Mapping]] = ..., rewards_eligible: _Optional[bool] = ..., player_tracked_stats: _Optional[_Iterable[_Union[CMsgTrackedStat, _Mapping]]] = ..., accolades: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.PlayerAccolade, _Mapping]]] = ..., mvp_rank: _Optional[int] = ..., earned_holiday_award_2025: _Optional[bool] = ..., power_up_buffs: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.PowerUpBuff, _Mapping]]] = ...) -> None: ...
    class Teams(_message.Message):
        __slots__ = ("team", "team_tracked_stats")
        TEAM_FIELD_NUMBER: _ClassVar[int]
        TEAM_TRACKED_STATS_FIELD_NUMBER: _ClassVar[int]
        team: ECitadelLobbyTeam
        team_tracked_stats: _containers.RepeatedCompositeFieldContainer[CMsgTrackedStat]
        def __init__(self, team: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., team_tracked_stats: _Optional[_Iterable[_Union[CMsgTrackedStat, _Mapping]]] = ...) -> None: ...
    class Objective(_message.Message):
        __slots__ = ("legacy_objective_id", "destroyed_time_s", "creep_damage", "creep_damage_mitigated", "player_damage", "player_damage_mitigated", "first_damage_time_s", "team_objective_id", "team", "player_spirit_damage")
        LEGACY_OBJECTIVE_ID_FIELD_NUMBER: _ClassVar[int]
        DESTROYED_TIME_S_FIELD_NUMBER: _ClassVar[int]
        CREEP_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        CREEP_DAMAGE_MITIGATED_FIELD_NUMBER: _ClassVar[int]
        PLAYER_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        PLAYER_DAMAGE_MITIGATED_FIELD_NUMBER: _ClassVar[int]
        FIRST_DAMAGE_TIME_S_FIELD_NUMBER: _ClassVar[int]
        TEAM_OBJECTIVE_ID_FIELD_NUMBER: _ClassVar[int]
        TEAM_FIELD_NUMBER: _ClassVar[int]
        PLAYER_SPIRIT_DAMAGE_FIELD_NUMBER: _ClassVar[int]
        legacy_objective_id: ECitadelObjective
        destroyed_time_s: int
        creep_damage: int
        creep_damage_mitigated: int
        player_damage: int
        player_damage_mitigated: int
        first_damage_time_s: int
        team_objective_id: ECitadelTeamObjective
        team: ECitadelLobbyTeam
        player_spirit_damage: int
        def __init__(self, legacy_objective_id: _Optional[_Union[ECitadelObjective, str]] = ..., destroyed_time_s: _Optional[int] = ..., creep_damage: _Optional[int] = ..., creep_damage_mitigated: _Optional[int] = ..., player_damage: _Optional[int] = ..., player_damage_mitigated: _Optional[int] = ..., first_damage_time_s: _Optional[int] = ..., team_objective_id: _Optional[_Union[ECitadelTeamObjective, str]] = ..., team: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., player_spirit_damage: _Optional[int] = ...) -> None: ...
    class MidBoss(_message.Message):
        __slots__ = ("team_killed", "team_claimed", "destroyed_time_s")
        TEAM_KILLED_FIELD_NUMBER: _ClassVar[int]
        TEAM_CLAIMED_FIELD_NUMBER: _ClassVar[int]
        DESTROYED_TIME_S_FIELD_NUMBER: _ClassVar[int]
        team_killed: ECitadelLobbyTeam
        team_claimed: ECitadelLobbyTeam
        destroyed_time_s: int
        def __init__(self, team_killed: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., team_claimed: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., destroyed_time_s: _Optional[int] = ...) -> None: ...
    class Pause(_message.Message):
        __slots__ = ("game_time_s", "pause_duration_s", "player_slot")
        GAME_TIME_S_FIELD_NUMBER: _ClassVar[int]
        PAUSE_DURATION_S_FIELD_NUMBER: _ClassVar[int]
        PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        game_time_s: int
        pause_duration_s: int
        player_slot: int
        def __init__(self, game_time_s: _Optional[int] = ..., pause_duration_s: _Optional[int] = ..., player_slot: _Optional[int] = ...) -> None: ...
    class WatchedDeathReplay(_message.Message):
        __slots__ = ("game_time_s", "player_slot")
        GAME_TIME_S_FIELD_NUMBER: _ClassVar[int]
        PLAYER_SLOT_FIELD_NUMBER: _ClassVar[int]
        game_time_s: int
        player_slot: int
        def __init__(self, game_time_s: _Optional[int] = ..., player_slot: _Optional[int] = ...) -> None: ...
    class StreetBrawlRound(_message.Message):
        __slots__ = ("round_duration_s", "winning_team")
        ROUND_DURATION_S_FIELD_NUMBER: _ClassVar[int]
        WINNING_TEAM_FIELD_NUMBER: _ClassVar[int]
        round_duration_s: int
        winning_team: ECitadelLobbyTeam
        def __init__(self, round_duration_s: _Optional[int] = ..., winning_team: _Optional[_Union[ECitadelLobbyTeam, str]] = ...) -> None: ...
    class MatchInfo(_message.Message):
        __slots__ = ("duration_s", "match_outcome", "winning_team", "players", "start_time", "match_id", "legacy_objectives_mask", "game_mode", "match_mode", "objectives", "match_paths", "damage_matrix", "match_pauses", "custom_user_stats", "watched_death_replays", "objectives_mask_team0", "objectives_mask_team1", "mid_boss", "is_high_skill_range_parties", "low_pri_pool", "new_player_pool", "average_badge_team0", "average_badge_team1", "game_mode_version", "rewards_eligible", "not_scored", "team_score", "match_tracked_stats", "teams", "bot_difficulty", "street_brawl_rounds")
        DURATION_S_FIELD_NUMBER: _ClassVar[int]
        MATCH_OUTCOME_FIELD_NUMBER: _ClassVar[int]
        WINNING_TEAM_FIELD_NUMBER: _ClassVar[int]
        PLAYERS_FIELD_NUMBER: _ClassVar[int]
        START_TIME_FIELD_NUMBER: _ClassVar[int]
        MATCH_ID_FIELD_NUMBER: _ClassVar[int]
        LEGACY_OBJECTIVES_MASK_FIELD_NUMBER: _ClassVar[int]
        GAME_MODE_FIELD_NUMBER: _ClassVar[int]
        MATCH_MODE_FIELD_NUMBER: _ClassVar[int]
        OBJECTIVES_FIELD_NUMBER: _ClassVar[int]
        MATCH_PATHS_FIELD_NUMBER: _ClassVar[int]
        DAMAGE_MATRIX_FIELD_NUMBER: _ClassVar[int]
        MATCH_PAUSES_FIELD_NUMBER: _ClassVar[int]
        CUSTOM_USER_STATS_FIELD_NUMBER: _ClassVar[int]
        WATCHED_DEATH_REPLAYS_FIELD_NUMBER: _ClassVar[int]
        OBJECTIVES_MASK_TEAM0_FIELD_NUMBER: _ClassVar[int]
        OBJECTIVES_MASK_TEAM1_FIELD_NUMBER: _ClassVar[int]
        MID_BOSS_FIELD_NUMBER: _ClassVar[int]
        IS_HIGH_SKILL_RANGE_PARTIES_FIELD_NUMBER: _ClassVar[int]
        LOW_PRI_POOL_FIELD_NUMBER: _ClassVar[int]
        NEW_PLAYER_POOL_FIELD_NUMBER: _ClassVar[int]
        AVERAGE_BADGE_TEAM0_FIELD_NUMBER: _ClassVar[int]
        AVERAGE_BADGE_TEAM1_FIELD_NUMBER: _ClassVar[int]
        GAME_MODE_VERSION_FIELD_NUMBER: _ClassVar[int]
        REWARDS_ELIGIBLE_FIELD_NUMBER: _ClassVar[int]
        NOT_SCORED_FIELD_NUMBER: _ClassVar[int]
        TEAM_SCORE_FIELD_NUMBER: _ClassVar[int]
        MATCH_TRACKED_STATS_FIELD_NUMBER: _ClassVar[int]
        TEAMS_FIELD_NUMBER: _ClassVar[int]
        BOT_DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
        STREET_BRAWL_ROUNDS_FIELD_NUMBER: _ClassVar[int]
        duration_s: int
        match_outcome: CMsgMatchMetaDataContents.EMatchOutcome
        winning_team: ECitadelLobbyTeam
        players: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Players]
        start_time: int
        match_id: int
        legacy_objectives_mask: int
        game_mode: ECitadelGameMode
        match_mode: ECitadelMatchMode
        objectives: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Objective]
        match_paths: CMsgMatchPlayerPathsData
        damage_matrix: CMsgMatchPlayerDamageMatrix
        match_pauses: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Pause]
        custom_user_stats: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.CustomUserStatInfo]
        watched_death_replays: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.WatchedDeathReplay]
        objectives_mask_team0: int
        objectives_mask_team1: int
        mid_boss: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.MidBoss]
        is_high_skill_range_parties: bool
        low_pri_pool: bool
        new_player_pool: bool
        average_badge_team0: int
        average_badge_team1: int
        game_mode_version: int
        rewards_eligible: bool
        not_scored: bool
        team_score: _containers.RepeatedScalarFieldContainer[int]
        match_tracked_stats: _containers.RepeatedCompositeFieldContainer[CMsgTrackedStat]
        teams: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.Teams]
        bot_difficulty: ECitadelBotDifficulty
        street_brawl_rounds: _containers.RepeatedCompositeFieldContainer[CMsgMatchMetaDataContents.StreetBrawlRound]
        def __init__(self, duration_s: _Optional[int] = ..., match_outcome: _Optional[_Union[CMsgMatchMetaDataContents.EMatchOutcome, str]] = ..., winning_team: _Optional[_Union[ECitadelLobbyTeam, str]] = ..., players: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Players, _Mapping]]] = ..., start_time: _Optional[int] = ..., match_id: _Optional[int] = ..., legacy_objectives_mask: _Optional[int] = ..., game_mode: _Optional[_Union[ECitadelGameMode, str]] = ..., match_mode: _Optional[_Union[ECitadelMatchMode, str]] = ..., objectives: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Objective, _Mapping]]] = ..., match_paths: _Optional[_Union[CMsgMatchPlayerPathsData, _Mapping]] = ..., damage_matrix: _Optional[_Union[CMsgMatchPlayerDamageMatrix, _Mapping]] = ..., match_pauses: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Pause, _Mapping]]] = ..., custom_user_stats: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.CustomUserStatInfo, _Mapping]]] = ..., watched_death_replays: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.WatchedDeathReplay, _Mapping]]] = ..., objectives_mask_team0: _Optional[int] = ..., objectives_mask_team1: _Optional[int] = ..., mid_boss: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.MidBoss, _Mapping]]] = ..., is_high_skill_range_parties: _Optional[bool] = ..., low_pri_pool: _Optional[bool] = ..., new_player_pool: _Optional[bool] = ..., average_badge_team0: _Optional[int] = ..., average_badge_team1: _Optional[int] = ..., game_mode_version: _Optional[int] = ..., rewards_eligible: _Optional[bool] = ..., not_scored: _Optional[bool] = ..., team_score: _Optional[_Iterable[int]] = ..., match_tracked_stats: _Optional[_Iterable[_Union[CMsgTrackedStat, _Mapping]]] = ..., teams: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.Teams, _Mapping]]] = ..., bot_difficulty: _Optional[_Union[ECitadelBotDifficulty, str]] = ..., street_brawl_rounds: _Optional[_Iterable[_Union[CMsgMatchMetaDataContents.StreetBrawlRound, _Mapping]]] = ...) -> None: ...
    MATCH_INFO_FIELD_NUMBER: _ClassVar[int]
    match_info: CMsgMatchMetaDataContents.MatchInfo
    def __init__(self, match_info: _Optional[_Union[CMsgMatchMetaDataContents.MatchInfo, _Mapping]] = ...) -> None: ...

class CMsgMatchMetaData(_message.Message):
    __slots__ = ("version", "match_details", "match_id")
    VERSION_FIELD_NUMBER: _ClassVar[int]
    MATCH_DETAILS_FIELD_NUMBER: _ClassVar[int]
    MATCH_ID_FIELD_NUMBER: _ClassVar[int]
    version: int
    match_details: bytes
    match_id: int
    def __init__(self, version: _Optional[int] = ..., match_details: _Optional[bytes] = ..., match_id: _Optional[int] = ...) -> None: ...

class CMsgMapLine(_message.Message):
    __slots__ = ("x", "y", "initial")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    INITIAL_FIELD_NUMBER: _ClassVar[int]
    x: int
    y: int
    initial: bool
    def __init__(self, x: _Optional[int] = ..., y: _Optional[int] = ..., initial: _Optional[bool] = ...) -> None: ...

class CMsgAccountHeroStats(_message.Message):
    __slots__ = ("hero_id", "stat_id", "total_value", "medals_bronze", "medals_silver", "medals_gold")
    HERO_ID_FIELD_NUMBER: _ClassVar[int]
    STAT_ID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_VALUE_FIELD_NUMBER: _ClassVar[int]
    MEDALS_BRONZE_FIELD_NUMBER: _ClassVar[int]
    MEDALS_SILVER_FIELD_NUMBER: _ClassVar[int]
    MEDALS_GOLD_FIELD_NUMBER: _ClassVar[int]
    hero_id: int
    stat_id: _containers.RepeatedScalarFieldContainer[int]
    total_value: _containers.RepeatedScalarFieldContainer[int]
    medals_bronze: _containers.RepeatedScalarFieldContainer[int]
    medals_silver: _containers.RepeatedScalarFieldContainer[int]
    medals_gold: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, hero_id: _Optional[int] = ..., stat_id: _Optional[_Iterable[int]] = ..., total_value: _Optional[_Iterable[int]] = ..., medals_bronze: _Optional[_Iterable[int]] = ..., medals_silver: _Optional[_Iterable[int]] = ..., medals_gold: _Optional[_Iterable[int]] = ...) -> None: ...

class CMsgAccountBookStats(_message.Message):
    __slots__ = ("book_id", "book_xp", "book_max_xp")
    BOOK_ID_FIELD_NUMBER: _ClassVar[int]
    BOOK_XP_FIELD_NUMBER: _ClassVar[int]
    BOOK_MAX_XP_FIELD_NUMBER: _ClassVar[int]
    book_id: int
    book_xp: int
    book_max_xp: int
    def __init__(self, book_id: _Optional[int] = ..., book_xp: _Optional[int] = ..., book_max_xp: _Optional[int] = ...) -> None: ...

class CMsgAccountStats(_message.Message):
    __slots__ = ("account_id", "stats")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    stats: _containers.RepeatedCompositeFieldContainer[CMsgAccountHeroStats]
    def __init__(self, account_id: _Optional[int] = ..., stats: _Optional[_Iterable[_Union[CMsgAccountHeroStats, _Mapping]]] = ...) -> None: ...

class CMsgTrackedStat(_message.Message):
    __slots__ = ("tracked_stat_id", "tracked_stat_value")
    TRACKED_STAT_ID_FIELD_NUMBER: _ClassVar[int]
    TRACKED_STAT_VALUE_FIELD_NUMBER: _ClassVar[int]
    tracked_stat_id: int
    tracked_stat_value: int
    def __init__(self, tracked_stat_id: _Optional[int] = ..., tracked_stat_value: _Optional[int] = ...) -> None: ...

class CMsgGCAccountData(_message.Message):
    __slots__ = ("account_id", "cheater_report_score")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    CHEATER_REPORT_SCORE_FIELD_NUMBER: _ClassVar[int]
    account_id: int
    cheater_report_score: float
    def __init__(self, account_id: _Optional[int] = ..., cheater_report_score: _Optional[float] = ...) -> None: ...

class CMsgHeroBuild(_message.Message):
    __slots__ = ("hero_build_id", "hero_id", "author_account_id", "last_updated_timestamp", "name", "description", "language", "version", "origin_build_id", "details", "tags", "development_build", "publish_timestamp")
    class BuildModEntry(_message.Message):
        __slots__ = ("ability_id", "annotation", "required_flex_slots", "sell_priority", "imbue_target_ability_id")
        ABILITY_ID_FIELD_NUMBER: _ClassVar[int]
        ANNOTATION_FIELD_NUMBER: _ClassVar[int]
        REQUIRED_FLEX_SLOTS_FIELD_NUMBER: _ClassVar[int]
        SELL_PRIORITY_FIELD_NUMBER: _ClassVar[int]
        IMBUE_TARGET_ABILITY_ID_FIELD_NUMBER: _ClassVar[int]
        ability_id: int
        annotation: str
        required_flex_slots: int
        sell_priority: int
        imbue_target_ability_id: int
        def __init__(self, ability_id: _Optional[int] = ..., annotation: _Optional[str] = ..., required_flex_slots: _Optional[int] = ..., sell_priority: _Optional[int] = ..., imbue_target_ability_id: _Optional[int] = ...) -> None: ...
    class BuildModCategory(_message.Message):
        __slots__ = ("mods", "name", "description", "width", "height", "optional")
        MODS_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        WIDTH_FIELD_NUMBER: _ClassVar[int]
        HEIGHT_FIELD_NUMBER: _ClassVar[int]
        OPTIONAL_FIELD_NUMBER: _ClassVar[int]
        mods: _containers.RepeatedCompositeFieldContainer[CMsgHeroBuild.BuildModEntry]
        name: str
        description: str
        width: float
        height: float
        optional: bool
        def __init__(self, mods: _Optional[_Iterable[_Union[CMsgHeroBuild.BuildModEntry, _Mapping]]] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., width: _Optional[float] = ..., height: _Optional[float] = ..., optional: _Optional[bool] = ...) -> None: ...
    class CurrencyChange(_message.Message):
        __slots__ = ("ability_id", "currency_type", "delta", "annotation")
        ABILITY_ID_FIELD_NUMBER: _ClassVar[int]
        CURRENCY_TYPE_FIELD_NUMBER: _ClassVar[int]
        DELTA_FIELD_NUMBER: _ClassVar[int]
        ANNOTATION_FIELD_NUMBER: _ClassVar[int]
        ability_id: int
        currency_type: int
        delta: int
        annotation: str
        def __init__(self, ability_id: _Optional[int] = ..., currency_type: _Optional[int] = ..., delta: _Optional[int] = ..., annotation: _Optional[str] = ...) -> None: ...
    class AbilityOrder(_message.Message):
        __slots__ = ("currency_changes",)
        CURRENCY_CHANGES_FIELD_NUMBER: _ClassVar[int]
        currency_changes: _containers.RepeatedCompositeFieldContainer[CMsgHeroBuild.CurrencyChange]
        def __init__(self, currency_changes: _Optional[_Iterable[_Union[CMsgHeroBuild.CurrencyChange, _Mapping]]] = ...) -> None: ...
    class Details_V0(_message.Message):
        __slots__ = ("mod_categories", "ability_order")
        MOD_CATEGORIES_FIELD_NUMBER: _ClassVar[int]
        ABILITY_ORDER_FIELD_NUMBER: _ClassVar[int]
        mod_categories: _containers.RepeatedCompositeFieldContainer[CMsgHeroBuild.BuildModCategory]
        ability_order: CMsgHeroBuild.AbilityOrder
        def __init__(self, mod_categories: _Optional[_Iterable[_Union[CMsgHeroBuild.BuildModCategory, _Mapping]]] = ..., ability_order: _Optional[_Union[CMsgHeroBuild.AbilityOrder, _Mapping]] = ...) -> None: ...
    HERO_BUILD_ID_FIELD_NUMBER: _ClassVar[int]
    HERO_ID_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATED_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_BUILD_ID_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    DEVELOPMENT_BUILD_FIELD_NUMBER: _ClassVar[int]
    PUBLISH_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    hero_build_id: int
    hero_id: int
    author_account_id: int
    last_updated_timestamp: int
    name: str
    description: str
    language: int
    version: int
    origin_build_id: int
    details: CMsgHeroBuild.Details_V0
    tags: _containers.RepeatedScalarFieldContainer[int]
    development_build: bool
    publish_timestamp: int
    def __init__(self, hero_build_id: _Optional[int] = ..., hero_id: _Optional[int] = ..., author_account_id: _Optional[int] = ..., last_updated_timestamp: _Optional[int] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., language: _Optional[int] = ..., version: _Optional[int] = ..., origin_build_id: _Optional[int] = ..., details: _Optional[_Union[CMsgHeroBuild.Details_V0, _Mapping]] = ..., tags: _Optional[_Iterable[int]] = ..., development_build: _Optional[bool] = ..., publish_timestamp: _Optional[int] = ...) -> None: ...

class CMsgHeroBuildPreference(_message.Message):
    __slots__ = ("favorited", "ignored", "reported")
    FAVORITED_FIELD_NUMBER: _ClassVar[int]
    IGNORED_FIELD_NUMBER: _ClassVar[int]
    REPORTED_FIELD_NUMBER: _ClassVar[int]
    favorited: bool
    ignored: bool
    reported: bool
    def __init__(self, favorited: _Optional[bool] = ..., ignored: _Optional[bool] = ..., reported: _Optional[bool] = ...) -> None: ...

class CMsgHeroReleaseVoteTally(_message.Message):
    __slots__ = ("remaining_votes", "votes_cast", "daily_reward_time_stamp")
    REMAINING_VOTES_FIELD_NUMBER: _ClassVar[int]
    VOTES_CAST_FIELD_NUMBER: _ClassVar[int]
    DAILY_REWARD_TIME_STAMP_FIELD_NUMBER: _ClassVar[int]
    remaining_votes: int
    votes_cast: _containers.RepeatedScalarFieldContainer[int]
    daily_reward_time_stamp: int
    def __init__(self, remaining_votes: _Optional[int] = ..., votes_cast: _Optional[_Iterable[int]] = ..., daily_reward_time_stamp: _Optional[int] = ...) -> None: ...
