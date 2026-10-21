/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SHOP_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
