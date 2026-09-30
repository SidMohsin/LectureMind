export function displayNameFor(user, profile) {
  return profile?.display_name || user?.user_metadata?.full_name || user?.email?.split("@")[0] || "";
}

export function initialsFor(name) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  const letters = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0];
  return letters.toUpperCase();
}
