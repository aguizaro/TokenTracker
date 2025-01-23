# models.py
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Token(BaseModel):
    address: str
    name: str
    symbol: str


class Volume(BaseModel):
    h24: Optional[float] = None
    h6: Optional[float] = None
    h1: Optional[float] = None
    m5: Optional[float] = None


class PriceChange(BaseModel):
    m5: Optional[float] = None
    h1: Optional[float] = None
    h6: Optional[float] = None
    h24: Optional[float] = None


class Liquidity(BaseModel):
    usd: Optional[float] = None
    base: Optional[float] = None
    quote: Optional[float] = None


class Website(BaseModel):
    url: Optional[HttpUrl] = None


class Socials(BaseModel):
    type_: str = Field(..., alias="type")  # Use alias to map "type" to "type_"
    url: str


class Info(BaseModel):
    imageUrl: Optional[HttpUrl]
    header: Optional[str]
    openGraph: Optional[str]
    websites: List[Website] = []  # Default empty list if missing
    socials: List[Socials] = []  # Default empty list if missing


class Pair(BaseModel):
    chainId: str
    dexId: str
    url: Optional[HttpUrl] = None
    pairAddress: str
    baseToken: Token
    quoteToken: Token
    priceNative: Optional[str] = None
    priceUsd: Optional[str] = None
    volume: Optional[Volume] = None
    priceChange: Optional[PriceChange] = None
    liquidity: Optional[Liquidity] = None
    fdv: Optional[float] = None
    marketCap: Optional[float] = None
    pairCreatedAt: Optional[int] = None
    info: Optional[Info] = None  # Optional, can be None
    boosts: Optional[Dict] = {}  # Default empty dictionary if missing


class PairsResponse(BaseModel):
    schemaVersidn: str
    pairs: List[Pair]
