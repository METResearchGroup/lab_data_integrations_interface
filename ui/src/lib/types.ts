export type CollectionParams = {
  limit: number
  handles?: string[]
}

export type AppState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'success'; downloadUrl: string }
  | { status: 'error'; message: string }
