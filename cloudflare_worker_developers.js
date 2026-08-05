export default {
  async fetch(request) {
    return Response.redirect(
      "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/developers",
      301
    );
  },
};
