# Native individual media deletion evidence

Primary source is public AiSandboxAngularFrontend build SE3VK6s4aGU.2018.O. The cached project bundle c8a encoder at character offset 3691253 sets selected project field 3 and requested media IDs field 7; workflow IDs occupy field 2 and collections field 1. The permanent individual adapter omits workflow IDs and does not send unrequested siblings.

The first owned synthetic MP4 deletion received the expected empty BatchDeleteAssets acknowledgement. An immediate fresh project read still contained that exact fixture. A subsequent fresh read showed the fixture absent, and exact GetMedia returned HTTP 200 with native gRPC 5 not-found and no owned media reply. No deletion was repeated. This demonstrates effective media-only deletion for this owned synthetic upload and delayed visibility, not a guaranteed propagation time or complete support for every media/batch structure.

Acknowledgement and observed removal are separate facts. Bounded metadata-only polling may establish the latter; another mutation must never be used to resolve uncertainty. Original assets are not deletion fixtures. Upload readiness was also observed after allowing the native menu rather than requiring visibility of the classic settings button.
