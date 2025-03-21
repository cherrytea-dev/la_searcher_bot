from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str = Field(description='One-word description')
    age: Optional[int] = Field(None, description='Age in years')
    age_min: Optional[int] = Field(None, description='Minimum age in years')
    age_max: Optional[int] = Field(None, description='Maximum age in years')
    # TODO validation for age: ge=0, le=199
    display_name: str = Field(description='Display name + age')
    number_of_persons: int = Field(..., ge=-1, le=9, description='Number of persons in this group, -1 or 1-9')


class PersonsSummary(BaseModel):
    total_persons: Union[int, str] = Field(..., description="Total number of persons: 1-9, 'group', or 'undefined'")
    age_min: Optional[int] = Field(None, description='Minimum age across all persons')
    age_max: Optional[int] = Field(None, description='Maximum age across all persons')
    # TODO validation for age: ge=0, le=199
    total_name: str = Field(description='Name of the first person')
    total_display_name: str = Field(description='Display name + age (age range)')
    person: List[Person] = Field(default_factory=list)


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
    avia: Optional[bool] = Field(None, description='Only for search')
    status: Optional[str] = Field(None, description='Only for search / search reverse')
    persons: Optional[PersonsSummary] = Field(None, description='Only for search')
    locations: Optional[List[Location]] = Field(None, description='Only for search')
