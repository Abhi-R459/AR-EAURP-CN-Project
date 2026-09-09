"""Routing substrate for the common harness (Track 2).

Implements the machinery specified in base.pdf -- the custom control packets,
the packet-forwarding-ratio trust model with majority-vote revocation, the
energy-gated AODV route discovery scored by ``R_Score = a*T + b*E``, and ECC
payload protection.

This is *supporting infrastructure*, not one of the three graded
implementations. It exists because Track 2 needs a routing layer that actually
forwards packets hop by hop, and because the slander attack in the advancement
is defined in terms of PT_GID consensus.
"""
