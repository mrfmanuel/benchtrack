// Build-time settings (Vite `VITE_*` variables are public: never put secrets here).

/** Printed on the receipt and in the page headers. */
export const SHOP_NAME: string = import.meta.env.VITE_SHOP_NAME?.trim() || 'BenchTrack Repair';
