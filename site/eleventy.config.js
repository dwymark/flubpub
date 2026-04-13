module.exports = function(eleventyConfig) {
  eleventyConfig.addFilter("readableDate", (date) => {
    return new Date(date).toLocaleDateString("en-US", {
      year: "numeric", month: "short", day: "numeric"
    });
  });

  eleventyConfig.addCollection("pages", function(collectionApi) {
    return collectionApi
      .getFilteredByGlob("src/pages/*.md")
      .sort((a, b) => b.date - a.date);
  });

  return {
    dir: {
      input: "src",
      output: "_site",
    },
  };
};
