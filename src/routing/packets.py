"""Custom control packet types -- base.pdf 3.6.

The three hex codes are taken verbatim from the paper:

    PT_NID  0x81   Node Identification   -- node id, forwarding ratios, timestamp
    PT_GID  0x82   Group Identification  -- node ids with cumulative trust scores
    PT_CREV 0x83   Controlled Revocation -- id of a confirmed malicious node

Route discovery uses the standard AODV control set, kept separate so that the
protocol overhead of the trust machinery can be reported on its own.
"""

from dataclasses import dataclass, field

PT_NID = 0x81
PT_GID = 0x82
PT_CREV = 0x83

PT_RREQ = 0x01
PT_RREP = 0x02
PT_RERR = 0x03

PACKET_NAMES = {
    PT_NID: "PT_NID",
    PT_GID: "PT_GID",
    PT_CREV: "PT_CREV",
    PT_RREQ: "RREQ",
    PT_RREP: "RREP",
    PT_RERR: "RERR",
}

CONTROL_TYPES = (PT_NID, PT_GID, PT_CREV, PT_RREQ, PT_RREP, PT_RERR)


def packet_name(ptype):
    return PACKET_NAMES.get(int(ptype), "PT_{0:#04x}".format(int(ptype)))


@dataclass
class NidPacket:
    """base.pdf 3.6 -- periodic per-neighbour forwarding-ratio report."""

    ptype: int = PT_NID
    sender: int = -1
    timestamp: int = 0
    ratios: dict = field(default_factory=dict)   # neighbour id -> observed PFR


@dataclass
class GidPacket:
    """base.pdf 3.6 -- cumulative trust scores acting as a trust beacon."""

    ptype: int = PT_GID
    sender: int = -1
    timestamp: int = 0
    scores: dict = field(default_factory=dict)   # node id -> reported trust
    accusations: tuple = ()                      # node ids reported suspicious


@dataclass
class CrevPacket:
    """base.pdf 3.6 -- broadcast that a node has been revoked."""

    ptype: int = PT_CREV
    sender: int = -1
    timestamp: int = 0
    revoked: int = -1
    evidence: float = 0.0


@dataclass
class RouteRequest:
    """AODV RREQ carrying the accumulated route score (base.pdf 3.3)."""

    ptype: int = PT_RREQ
    rreq_id: int = 0
    source: int = -1
    destination: int = -1
    hops: tuple = ()
    score: float = 0.0


@dataclass
class RouteReply:
    """AODV RREP returned along the reverse path (base.pdf 3.4)."""

    ptype: int = PT_RREP
    source: int = -1
    destination: int = -1
    path: tuple = ()
    cumulative_score: float = 0.0
