import type { GeneratorApi } from "./contracts";
import { USE_MOCK_API } from "./config";
import { mockGeneratorApi } from "./mock/generatorApi";
import { realGeneratorApi } from "./api/generatorApi";

export const generatorApi: GeneratorApi = USE_MOCK_API ? mockGeneratorApi : realGeneratorApi;
export type { GenerationStatusResult } from "./contracts";
