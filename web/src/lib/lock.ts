// Target acquisition rules shared by the stream handler and the HUD.

export const LOCK_CONFIDENCE = 0.85;

/**
 * A swarm is "fresh" unless most of its accounts were already acquired before
 * the latest launch. Member overlap survives cluster re-identification, so an
 * old swarm never steals the lock from the one that was just launched.
 */
export function isFresh(members: Int32Array, acquired: Uint8Array) {
  if (!acquired.length) return true;
  let old = 0;
  for (let k = 0; k < members.length; k++) if (members[k] < acquired.length && acquired[members[k]]) old++;
  return old < 0.5 * members.length;
}
