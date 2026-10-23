"""Arguments of the git tools as the model sees them: type + description.
Every argument is required, with '' meaning "not used", so the schema also
works in OpenAI strict mode."""
from typing import Annotated

Repository = Annotated[str, "Repository folder relative to the project folder (e.g. 'project-core-lib'); '' = the project folder itself."]
