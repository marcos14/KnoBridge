const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Whether `value` is a UUID, as the API's id parameters require (anything else is a 422). */
export function isUuid(value: string | null): value is string {
  return value !== null && UUID.test(value);
}
