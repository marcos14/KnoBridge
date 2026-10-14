import { http, HttpResponse } from "msw";

import type { Widget, WidgetChanges, WidgetInput } from "@/lib/api/widgets";
import { normalizeOrigin, originIssues } from "@/lib/widgetOrigins";

import { makeProducts } from "../factories";
import {
  makeWidget,
  makeWidgets,
  WIDGET_SECRET,
  WIDGET_SECRET_CREATED_AT,
} from "../widgetFactories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const WIDGETS = "*/v1/workspaces/:workspaceId/widgets";
const WIDGET = "*/v1/workspaces/:workspaceId/widgets/:widgetId";
const SECRET = "*/v1/workspaces/:workspaceId/widgets/:widgetId/signing-secret";

/** Mutations of a widget, for `widgetActionFails`. */
export type WidgetAction = "create" | "update" | "delete" | "rotateSecret" | "removeSecret";

const ACTION_HANDLERS = {
  create: [http.post, WIDGETS],
  update: [http.patch, WIDGET],
  delete: [http.delete, WIDGET],
  rotateSecret: [http.post, SECRET],
  removeSecret: [http.delete, SECRET],
} as const;

/** Instant the store writes in `updated_at` and in a new secret. */
const NOW = WIDGET_SECRET_CREATED_AT;

/** The list as the API filters it: `query` (name), `product_id` and `active`. */
function filtered(request: Request, widgets: readonly Widget[]): Widget[] {
  const params = new URL(request.url).searchParams;
  const query = params.get("query")?.toLowerCase();
  const productId = params.get("product_id");
  const active = params.get("active");
  return widgets.filter(
    (widget) =>
      (query === undefined || widget.name.toLowerCase().includes(query)) &&
      (productId === null || widget.product_id === productId) &&
      (active === null || String(widget.active) === active),
  );
}

/** Origins as the API stores them (normalized), or the 422 it answers. */
function checkOrigins(origins: readonly string[]): string[] | Response {
  const issues = originIssues(origins);
  if (issues.length > 0) {
    return apiErrorResponse(422, "widget_origin_invalid", { origins: issues });
  }
  return origins.map((origin) => {
    const result = normalizeOrigin(origin);
    return "origin" in result ? result.origin : origin;
  });
}

/** GET list and detail of `widgets` (default: Portal interno and Site público); 404 for other ids. */
export function widgetsAs(widgets: Widget[] = makeWidgets()) {
  return [
    http.get(WIDGETS, ({ request }) => page(request, filtered(request, widgets))),
    http.get(WIDGET, ({ params }) => {
      const widget = widgets.find(({ id }) => id === params.widgetId);
      return widget === undefined ? apiErrorResponse(404, "not_found") : HttpResponse.json(widget);
    }),
  ];
}

/** GET of the list failing on the server (500). */
export const widgetsServerError = http.get(WIDGETS, () => apiErrorResponse(500, "internal_error"));

/** GET of a widget failing on the server (500). */
export const widgetServerError = http.get(WIDGET, () => apiErrorResponse(500, "internal_error"));

/** A widget mutation (`action`) refused with `status`, `code` and `details`. */
export function widgetActionFails(
  action: WidgetAction,
  status: number,
  code: string,
  details: unknown = null,
) {
  const [method, path] = ACTION_HANDLERS[action];
  return method(path, () => apiErrorResponse(status, code, details));
}

/**
 * Widgets that really change, with the backend's rules: `POST` adds one (409
 * `widget_name_taken`, 422 `widget_product_invalid` for a product not in `productIds`, 422
 * `widget_origin_invalid` with `details.origins`), `PATCH` applies the fields (`title: null` is
 * the product's name), `DELETE` removes it, `signing-secret` generates `WIDGET_SECRET` or removes
 * it. `created`, `changes`, `deleted`, `rotations`, `removals` and `listQueries` keep what was
 * asked.
 */
export function widgetStore(
  initial: Widget[] = makeWidgets(),
  productIds: string[] = makeProducts().map(({ id }) => id),
) {
  let widgets = [...initial];
  const created: WidgetInput[] = [];
  const changes: { widgetId: string; body: WidgetChanges }[] = [];
  const deleted: string[] = [];
  const rotations: string[] = [];
  const removals: string[] = [];
  const listQueries: URLSearchParams[] = [];
  const find = (id: unknown) => widgets.find((widget) => widget.id === id);
  const replace = (updated: Widget) => {
    widgets = widgets.map((widget) => (widget.id === updated.id ? updated : widget));
  };
  const products = makeProducts();
  const handlers = [
    http.get(WIDGETS, ({ request }) => {
      listQueries.push(new URL(request.url).searchParams);
      return page(request, filtered(request, widgets));
    }),
    http.get(WIDGET, ({ params }) => {
      const widget = find(params.widgetId);
      return widget === undefined ? apiErrorResponse(404, "not_found") : HttpResponse.json(widget);
    }),
    http.post(WIDGETS, async ({ request }) => {
      const body = (await request.json()) as WidgetInput;
      created.push(body);
      if (widgets.some(({ name }) => name === body.name)) {
        return apiErrorResponse(409, "widget_name_taken");
      }
      if (!productIds.includes(body.product_id)) {
        return apiErrorResponse(422, "widget_product_invalid");
      }
      const origins = checkOrigins(body.allowed_origins);
      if (origins instanceof Response) {
        return origins;
      }
      const widget = makeWidget({
        ...body,
        id: `00000000-0000-4000-8000-${String(900 + created.length).padStart(12, "0")}`,
        product_name: products.find(({ id }) => id === body.product_id)?.name ?? "",
        public_key: "kbp_novo0widget0000000000000",
        allowed_origins: origins,
        title: body.title ?? null,
        created_at: NOW,
        updated_at: NOW,
      });
      widgets = [...widgets, widget].sort((a, b) => a.name.localeCompare(b.name));
      return HttpResponse.json(widget, { status: 201 });
    }),
    http.patch(WIDGET, async ({ params, request }) => {
      const widget = find(params.widgetId);
      if (widget === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const body = (await request.json()) as WidgetChanges;
      changes.push({ widgetId: widget.id, body });
      if (Object.keys(body).length === 0) {
        return apiErrorResponse(422, "validation_error");
      }
      const origins =
        body.allowed_origins === undefined || body.allowed_origins === null
          ? widget.allowed_origins
          : checkOrigins(body.allowed_origins);
      if (origins instanceof Response) {
        return origins;
      }
      const defined = Object.fromEntries(
        Object.entries(body).filter(([key, value]) => value !== null || key === "title"),
      );
      const updated: Widget = {
        ...widget,
        ...defined,
        allowed_origins: origins,
        updated_at: NOW,
      };
      replace(updated);
      return HttpResponse.json(updated);
    }),
    http.delete(WIDGET, ({ params }) => {
      const widget = find(params.widgetId);
      if (widget === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      deleted.push(widget.id);
      widgets = widgets.filter(({ id }) => id !== widget.id);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(SECRET, ({ params }) => {
      const widget = find(params.widgetId);
      if (widget === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      rotations.push(widget.id);
      replace({ ...widget, signing_secret_configured: true, signing_secret_created_at: NOW });
      return HttpResponse.json({ secret: WIDGET_SECRET, created_at: NOW }, { status: 201 });
    }),
    http.delete(SECRET, ({ params }) => {
      const widget = find(params.widgetId);
      if (widget === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      removals.push(widget.id);
      replace({ ...widget, signing_secret_configured: false, signing_secret_created_at: null });
      return new HttpResponse(null, { status: 204 });
    }),
  ];
  return { handlers, created, changes, deleted, rotations, removals, listQueries };
}

/** Default handlers: list and detail of the default widgets, without state. */
export const widgetsHandlers = widgetsAs();
