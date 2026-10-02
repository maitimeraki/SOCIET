import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { IngestedDoc } from '../api/types'

export interface DraftDoc extends IngestedDoc {
  status: 'extracting' | 'ready' | 'failed'
  error?: string
  /** Original File for retry; absent for URL documents and after a page refresh (sessionStorage cannot hold Files). */
  file?: File
}

export interface DraftGraphSummary {
  chunks: number
  docs: number
  entityTypes: number
  relationTypes: number
}

interface DraftState {
  corpusName: string
  docs: DraftDoc[]
  datasetId: string | null
  ontologyJobId: string | null
  graphJobId: string | null
  graphSummary: DraftGraphSummary | null
  setCorpusName: (name: string) => void
  addDocs: (docs: DraftDoc[]) => void
  updateDoc: (documentId: string, patch: Partial<DraftDoc>) => void
  removeDoc: (documentId: string) => void
  setDatasetId: (id: string) => void
  setJobs: (patch: Partial<Pick<DraftState, 'ontologyJobId' | 'graphJobId'>>) => void
  setGraphSummary: (summary: DraftGraphSummary | null) => void
  clear: () => void
}

export const useDraftStore = create<DraftState>()(
  persist(
    (set, get) => ({
      corpusName: 'Untitled corpus',
      docs: [],
      datasetId: null,
      ontologyJobId: null,
      graphJobId: null,
      graphSummary: null,
      setCorpusName: (corpusName) => set({ corpusName }),
      addDocs: (docs) => set({ docs: [...get().docs, ...docs] }),
      updateDoc: (documentId, patch) =>
        set({ docs: get().docs.map((doc) => (doc.document_id === documentId ? { ...doc, ...patch } : doc)) }),
      removeDoc: (documentId) => set({ docs: get().docs.filter((doc) => doc.document_id !== documentId) }),
      setDatasetId: (datasetId) => set({ datasetId }),
      setJobs: (patch) => set(patch),
      setGraphSummary: (graphSummary) => set({ graphSummary }),
      // Keep datasetId: the run views reference the corpus long after the wizard is done.
      clear: () => set({ docs: [], ontologyJobId: null, graphJobId: null, graphSummary: null, corpusName: 'Untitled corpus' }),
    }),
    {
      name: 'chamber.draft',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        corpusName: state.corpusName,
        docs: state.docs.map((doc) => ({ ...doc, file: undefined })),
        datasetId: state.datasetId,
        ontologyJobId: state.ontologyJobId,
        graphJobId: state.graphJobId,
        graphSummary: state.graphSummary,
      }),
    },
  ),
)
