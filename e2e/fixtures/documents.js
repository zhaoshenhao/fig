export const mockUploadResponse = {
  status: "ok",
  file: "test_guide.pdf",
  collection: "auto_film",
  chunks: 42,
  rebuilt: false,
};

export const mockScanResponse = {
  status: "ok",
  directory: "/data/documents",
  collection: "auto_film",
  chunks: 128,
  rebuilt: false,
};

export const mockUploadError = {
  status: "error",
  error: "invalid file format",
};
