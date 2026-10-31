from enum import Enum

from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str = Field(description='One-word description')
    age: int | None = Field(None, description='Age in years')
    age_min: int | None = Field(None, description='Minimum age in years')
    age_max: int | None = Field(None, description='Maximum age in years')
    # TODO validation for age: ge=0, le=199
    display_name: str = Field(description='Display name + age')
    number_of_persons: int = Field(..., ge=-1, le=9, description='Number of persons in this group, -1 or 1-9')


class PersonsSummary(BaseModel):
    total_persons: int | str = Field(..., description="Total number of persons: 1-9, 'group', or 'undefined'")
    age_min: int | None = Field(None, description='Minimum age across all persons')
    age_max: int | None = Field(None, description='Maximum age across all persons')
    # TODO validation for age: ge=0, le=199
    total_name: str = Field(description='Name of the first person')
    total_display_name: str = Field(description='Display name + age (age range)')
    person: list[Person] = Field(default_factory=list)


class Location(BaseModel):
    address: str


class RecognitionTopicType(str, Enum):
    search = 'search'
    search_reverse = 'search reverse'
    search_patrol = 'search patrol'
    search_training = 'search training'
    event = 'event'
    info = 'info'
    unrecognized = 'UNRECOGNIZED'


class RecognitionResult(BaseModel):
    topic_type: RecognitionTopicType = Field(RecognitionTopicType.unrecognized)
    avia: bool | None = Field(None, description='Only for search')
    status: str | None = Field(None, description='Only for search / search reverse')
    persons: PersonsSummary | None = Field(None, description='Only for search')
    locations: list[Location] | None = Field(None, description='Only for search')
