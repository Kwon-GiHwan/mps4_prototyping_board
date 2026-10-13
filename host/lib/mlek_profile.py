"""Frozen measurement profile (config/mlek_baseline.json) -> pmwl.knobs() arguments. Used by the packer (to build
blobs) and the baseline gate (to know which knob words a blob must carry)."""
from __future__ import annotations


def parse_ports(text: str | None) -> dict | None:
    """'cmd=ext,const=ext,arena=ext,fast=sram' -> {'cmd': 'ext', ...}"""
    return dict(kv.split("=") for kv in text.split(",")) if text else None


def parse_axi_limit(text: str | None) -> dict | None:
    """'sram=0x20F0B,ext=0x21F3F' -> {'sram': 0x20F0B, 'ext': 0x21F3F}"""
    return {kv.split("=")[0]: int(kv.split("=")[1], 0) for kv in text.split(",")} if text else None


def knob_args(prof: dict) -> dict:
    k = prof["knobs"]
    return dict(axi=None, ports=parse_ports(k["ports"]), axi_limit=parse_axi_limit(k["axi_limit"]),
                power_ctrl=k["power_ctrl"], fast_base=int(k["fast_base"], 0), ta_profile=prof["ta_profile"])
