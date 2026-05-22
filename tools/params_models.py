from pydantic import BaseModel, Field


class CalculatorParams(BaseModel):
    expression: str = Field(
        description="The mathematical expression to evaluate, for example: '2 + 3 * 4'.",
        min_length=1,
    )

class DateParams(BaseModel):
    day_offset: int = Field(
        default=0,
        description="The number of days to offset from current system date, for example : 0 - today , 1 - tomorrow etc.",
        ge=0,
    )


class LatestNewsParams(BaseModel):
    location: str = Field(
        description="The city, region, or country to search local news for, for example: 'Bucharest'.",
        min_length=2,
    )
    topic: str | None = Field(
        default=None,
        description="Optional news topic to narrow the search, for example: 'transport', 'sports', or 'weather'.",
    )
    max_results: int = Field(
        default=5,
        description="Maximum number of news headlines to return.",
        ge=1,
        le=10,
    )


class PageParams(BaseModel):
    url: str = Field(
        description="The article or web page URL to fetch.",
        min_length=10,
    )
    max_chars: int = Field(
        default=4000,
        description="Maximum number of readable text characters to return.",
        ge=500,
        le=10000,
    )

class TimeParams(BaseModel):
    include_seconds: bool = Field(
        default=True,
        description="Whether to include seconds in the returned local time.",
    )