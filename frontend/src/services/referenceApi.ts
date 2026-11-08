import type { ReferenceApi } from "./contracts";
import { USE_MOCK_API } from "./config";
import { mockReferenceApi } from "./mock/referenceApi";
import { realReferenceApi } from "./api/referenceApi";

export const referenceApi: ReferenceApi = USE_MOCK_API ? mockReferenceApi : realReferenceApi;
