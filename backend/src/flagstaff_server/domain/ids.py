# Shared here rather than in each module so a flag can name its environments, and an audit
# entry everything, without importing them.
from typing import NewType
from uuid import UUID

ProjectId = NewType("ProjectId", UUID)
EnvironmentId = NewType("EnvironmentId", UUID)
FlagId = NewType("FlagId", UUID)
ApiKeyId = NewType("ApiKeyId", UUID)
AuditEntryId = NewType("AuditEntryId", UUID)
