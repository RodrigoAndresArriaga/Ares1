# shared contract typing helpers
from typing import Annotated

from pydantic import ConfigDict, Field

CONTRACT_CONFIG = ConfigDict(extra="forbid")

StrictInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]
