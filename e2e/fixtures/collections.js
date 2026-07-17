export const mockCollections = ["auto_film", "default", "car_film_v2"];

export const mockCollectionInfo = (name) => ({
  name,
  vectors_count: 156,
  segments_count: 3,
  points_count: 156,
  status: "green",
});

export const mockBrowseResults = {
  collection: "auto_film",
  points: [
    { id: 1, score: null, text: "隔热膜选购指南：关注隔热率、透光率和紫外线阻隔率", source: "guide.md" },
    { id: 2, score: null, text: "威固VK70前挡膜参数说明", source: "products.md" },
  ],
  next_offset: 2,
};

export const mockSearchResults = (query) => ({
  collection: "auto_film",
  query,
  points: [
    { id: 3, score: 0.95, text: `关于「${query}」的最佳搜索结果`, source: "faq.md" },
    { id: 5, score: 0.87, text: "其他相关条目", source: "manual.md" },
  ],
});

export const mockCollectionCount = (name) => ({
  collection: name,
  count: 156,
});
