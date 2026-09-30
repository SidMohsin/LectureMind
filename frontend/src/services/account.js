import { api } from "./api";

export function getMe(options) {
  return api.get("/me", options);
}
