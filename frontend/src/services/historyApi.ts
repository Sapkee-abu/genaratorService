import type { HistoryApi } from "./contracts";
import { USE_MOCK_API } from "./config";
import { mockHistoryApi } from "./mock/historyApi";
import { realHistoryApi } from "./api/historyApi";

export const historyApi: HistoryApi = USE_MOCK_API ? mockHistoryApi : realHistoryApi;
