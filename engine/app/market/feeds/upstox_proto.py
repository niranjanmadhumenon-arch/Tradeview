"""Minimal decoder for Upstox Market Data Feed V3 protobuf messages.

Only the last-traded-price block is read, so this walks the protobuf wire
format directly instead of pulling in generated classes. Field numbers follow
Upstox's published MarketDataFeed.proto (V3):

  FeedResponse { type=1; map<string, Feed> feeds=2; currentTs=3; marketInfo=4 }
  Feed         { LTPC ltpc=1; FullFeed fullFeed=2; FirstLevelWithGreeks firstLevelWithGreeks=3 }
  FullFeed     { MarketFullFeed marketFF=1; IndexFullFeed indexFF=2 }   (each: LTPC ltpc=1)
  FirstLevelWithGreeks { LTPC ltpc=1; ... }
  LTPC         { double ltp=1; int64 ltt=2; int64 ltq=3; double cp=4 }
"""
from __future__ import annotations

import struct
from typing import Iterator


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, i
        shift += 7


def _fields(buf: bytes) -> Iterator[tuple[int, int, object]]:
    i = 0
    while i < len(buf):
        tag, i = _varint(buf, i)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 1:
            value, i = buf[i : i + 8], i + 8
        elif wire == 2:
            size, i = _varint(buf, i)
            value, i = buf[i : i + size], i + size
        elif wire == 5:
            value, i = buf[i : i + 4], i + 4
        else:
            raise ValueError(f"Unsupported protobuf wire type {wire}")
        yield number, wire, value


def _ltpc(buf: bytes) -> dict:
    out = {"ltp": 0.0, "cp": 0.0, "ltt": 0}
    for number, wire, value in _fields(buf):
        if number == 1 and wire == 1:
            out["ltp"] = struct.unpack("<d", value)[0]
        elif number == 4 and wire == 1:
            out["cp"] = struct.unpack("<d", value)[0]
        elif number == 2 and wire == 0:
            out["ltt"] = value
    return out


def _first(buf: bytes, numbers: tuple[int, ...]) -> bytes | None:
    for number, wire, value in _fields(buf):
        if number in numbers and wire == 2:
            return value
    return None


def _feed_ltpc(feed: bytes) -> dict | None:
    for number, wire, value in _fields(feed):
        if wire != 2:
            continue
        if number == 1:
            return _ltpc(value)
        if number == 2:  # FullFeed -> marketFF | indexFF -> ltpc
            inner = _first(value, (1, 2))
            block = _first(inner, (1,)) if inner else None
            return _ltpc(block) if block else None
        if number == 3:  # FirstLevelWithGreeks -> ltpc
            block = _first(value, (1,))
            return _ltpc(block) if block else None
    return None


def decode_feed_response(buf: bytes) -> dict[str, dict]:
    """Returns {instrument_key: {"ltp", "cp", "ltt"}} for every feed in the message."""
    out: dict[str, dict] = {}
    for number, wire, entry in _fields(buf):
        if number != 2 or wire != 2:
            continue
        key, feed = None, None
        for n, w, v in _fields(entry):
            if n == 1 and w == 2:
                key = v.decode("utf-8")
            elif n == 2 and w == 2:
                feed = v
        if key and feed is not None:
            ltpc = _feed_ltpc(feed)
            if ltpc and ltpc["ltp"] > 0:
                out[key] = ltpc
    return out
