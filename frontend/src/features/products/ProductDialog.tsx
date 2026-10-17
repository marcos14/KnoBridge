import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle } from "lucide-react";
import { type ReactElement, type ReactNode, useId, useMemo, useState } from "react";
import { type Control, useController, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type Product, useCreateProduct, useUpdateProduct } from "@/lib/api/products";
import { useCollections } from "@/lib/api/collections";

import {
  PRODUCT_TONES,
  productBody,
  productFormDefaults,
  productFormSchema,
  type ProductFormValues,
} from "./productForm";
import { RetrievalFields } from "./RetrievalFields";
import { webhookApiErrorText } from "./ticketWebhook";
import { TicketWebhookFields } from "./TicketWebhookFields";
import { TicketWebhookPanel } from "./TicketWebhookPanel";

interface ProductDialogProps {
  workspaceId: string;
  /** The product to edit; absent, the dialog creates one. */
  product?: Product;
  /** The element that opens the dialog (a `Button`); absent, the dialog opens on its own. */
  trigger?: ReactElement;
  /** Opens at once, without a trigger (editing the copy right after "Duplicar"). */
  defaultOpen?: boolean;
  /** Called when the dialog closes (saved or dismissed). */
  onClosed?: () => void;
  /** Owners and admins generate the webhook secret (a credential); editors only test it. */
  canManageSecret: boolean;
  /**
   * Whether the instance has a reranker, for a new product (an edit reads its own
   * `rerank_available`); `undefined` when no product says it yet.
   */
  rerankAvailable?: boolean;
  onSaved: (product: Product) => void;
}

/**
 * Create or edit a product (the model and its instructions are the workspace levels'):
 * collections, extra instructions, behavior, the ticket webhook and
 * whether it is active. Editing also offers the webhook secret and the test delivery.
 */
export function ProductDialog({
  workspaceId,
  product,
  trigger,
  canManageSecret,
  rerankAvailable,
  onSaved,
  defaultOpen = false,
  onClosed,
}: ProductDialogProps) {
  const { t } = useTranslation();
  const [open, setOpenState] = useState(defaultOpen);
  const editing = product !== undefined;
  const create = useCreateProduct(workspaceId);
  const update = useUpdateProduct(workspaceId);
  const save = editing ? update : create;
  const schema = useMemo(() => productFormSchema(t), [t]);
  const defaults = () => productFormDefaults(product);
  const form = useForm<ProductFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaults(),
  });

  function setOpen(next: boolean) {
    setOpenState(next);
    if (!next) {
      onClosed?.();
    }
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      form.reset(defaults());
      save.reset();
    }
  }

  function onSubmit(values: ProductFormValues) {
    const body = productBody(values, product);
    const done = {
      onSuccess: (saved: Product) => {
        setOpen(false);
        onSaved(saved);
      },
    };
    if (editing) {
      update.mutate({ productId: product.id, changes: body }, done);
    } else {
      create.mutate(body, done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger !== undefined && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {editing ? t("products.form.editTitle") : t("products.form.createTitle")}
          </DialogTitle>
          <DialogDescription>{t("products.form.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {save.isError && <FormAlert message={webhookApiErrorText(save.error, t)} />}
            <TextField control={form.control} name="name" label={t("products.form.name")} />
            <TextField
              control={form.control}
              name="description"
              rows={2}
              label={t("products.form.summary")}
            />
            <TextField
              control={form.control}
              name="instructions"
              rows={6}
              label={t("products.form.instructions")}
              description={t("products.form.instructionsHint")}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField
                control={form.control}
                name="language"
                label={t("products.form.language")}
                description={t("products.form.languageHint")}
              />
              <ToneField control={form.control} />
            </div>
            <CollectionsField control={form.control} workspaceId={workspaceId} />
            <RetrievalFields
              control={form.control}
              product={product}
              rerankAvailable={product?.rerank_available ?? rerankAvailable}
            />
            <TextField
              control={form.control}
              name="noSourceMessage"
              rows={3}
              label={t("products.form.noSourceMessage")}
              description={t("products.form.noSourceMessageHint")}
            />
            <TicketWebhookFields control={form.control} />
            {editing && (
              <TicketWebhookPanel
                workspaceId={workspaceId}
                product={product}
                canManageSecret={canManageSecret}
              />
            )}
            <FormField
              control={form.control}
              name="active"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start gap-3">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={(checked) => {
                        field.onChange(checked === true);
                      }}
                    />
                  </FormControl>
                  <div className="flex flex-col gap-1">
                    <FormLabel>{t("products.form.active")}</FormLabel>
                    <FormDescription>{t("products.form.activeHint")}</FormDescription>
                  </div>
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("products.form.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? t("auth.submitting") : t("products.form.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

interface FieldProps {
  control: Control<ProductFormValues>;
}

/**
 * The collections the product answers from, as checkboxes. Mounted only with the dialog open,
 * so the list is fetched when someone edits a product, not for every row of the table.
 */
function CollectionsField({ control, workspaceId }: FieldProps & { workspaceId: string }) {
  const { t } = useTranslation();
  const idPrefix = useId();
  const collections = useCollections(workspaceId);
  const { field } = useController({ control, name: "collectionIds" });
  const selected = field.value;

  function toggle(collectionId: string, checked: boolean) {
    field.onChange(
      checked ? [...selected, collectionId] : selected.filter((item) => item !== collectionId),
    );
  }

  let options: ReactNode;
  if (collections.isPending) {
    options = (
      <p role="status" className="text-sm">
        {t("products.form.collectionsLoading")}
      </p>
    );
  } else if (collections.isError) {
    options = (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm">
          {t("products.form.collectionsLoadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void collections.refetch();
          }}
        >
          {t("products.retry")}
        </Button>
      </div>
    );
  } else if (collections.data.length === 0) {
    options = (
      <p className="text-sm">
        {t("products.form.collectionsEmpty")}{" "}
        <Link to={`/w/${workspaceId}/collections`} className="underline underline-offset-4">
          {t("products.form.goToCollections")}
        </Link>
      </p>
    );
  } else {
    options = (
      <ul className="flex flex-col gap-2">
        {collections.data.map((collection) => {
          const id = `${idPrefix}-${collection.id}`;
          return (
            <li key={collection.id} className="flex items-start gap-3">
              <Checkbox
                id={id}
                checked={selected.includes(collection.id)}
                onCheckedChange={(checked) => {
                  toggle(collection.id, checked === true);
                }}
              />
              <div className="flex flex-col gap-0.5">
                <Label htmlFor={id}>{collection.name}</Label>
                {collection.description !== "" && (
                  <span className="text-muted-foreground text-xs">{collection.description}</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium">{t("products.form.collections")}</legend>
      <p className="text-muted-foreground text-sm">{t("products.form.collectionsHint")}</p>
      {options}
      {selected.length === 0 && (
        <p className="flex items-start gap-2 rounded-md border border-amber-500/50 px-3 py-2 text-sm">
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{t("products.form.noCollections")}</span>
        </p>
      )}
    </fieldset>
  );
}

function ToneField({ control }: FieldProps) {
  const { t } = useTranslation();
  return (
    <FormField
      control={control}
      name="tone"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("products.form.tone")}</FormLabel>
          <Select value={field.value} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {PRODUCT_TONES.map((tone) => (
                <SelectItem key={tone} value={tone}>
                  {t(`products.form.tones.${tone}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormItem>
      )}
    />
  );
}
