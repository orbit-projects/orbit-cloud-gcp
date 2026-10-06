# Copyright 2026-present Orbit Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Validated Google Cloud Asset Inventory configuration."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GCPCloudInventoryConfig(BaseModel):
    """Request and concurrency bounds; credentials use Google Application Default Credentials."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_concurrency: int = Field(default=8, ge=1, le=32)

    @model_validator(mode="after")
    def validate_timeout(self) -> GCPCloudInventoryConfig:
        """Reject a non-finite Google API request timeout."""
        if not math.isfinite(self.request_timeout_seconds):
            raise ValueError("request_timeout_seconds must be finite.")
        return self


__all__ = ["GCPCloudInventoryConfig"]
