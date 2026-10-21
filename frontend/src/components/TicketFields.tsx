import { DEVICE_TYPE_OPTIONS } from '../lib/format';
import type { FieldErrors } from '../lib/forms';
import type { TicketFormValues } from '../lib/ticketForm';
import { SelectField, TextAreaField, TextField } from './fields';
import type { DeviceType } from '../api/types';

interface Props {
  values: TicketFormValues;
  errors: FieldErrors;
  onChange: (values: TicketFormValues) => void;
}

/** Device and repair fields shared by "New ticket" and the ticket detail editor. */
export function TicketFields({ values, errors, onChange }: Props) {
  const set = (field: keyof TicketFormValues) => (value: string) =>
    onChange({ ...values, [field]: value });

  return (
    <div className="grid-2">
      <SelectField
        id="device_type"
        label="Device type"
        required
        value={values.device_type}
        error={errors.device_type}
        onChange={(e) => set('device_type')(e.target.value as DeviceType)}
      >
        {DEVICE_TYPE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </SelectField>
      <TextField
        id="brand"
        label="Brand"
        required
        maxLength={60}
        value={values.brand}
        error={errors.brand}
        onChange={(e) => set('brand')(e.target.value)}
      />
      <TextField
        id="model"
        label="Model"
        maxLength={60}
        value={values.model}
        error={errors.model}
        onChange={(e) => set('model')(e.target.value)}
      />
      <TextField
        id="serial_number"
        label="Serial number"
        maxLength={60}
        value={values.serial_number}
        error={errors.serial_number}
        onChange={(e) => set('serial_number')(e.target.value)}
      />
      <div className="span-2">
        <TextAreaField
          id="reported_issue"
          label="Reported issue"
          required
          maxLength={2000}
          value={values.reported_issue}
          error={errors.reported_issue}
          onChange={(e) => set('reported_issue')(e.target.value)}
        />
      </div>
      <div className="span-2">
        <TextAreaField
          id="diagnosis"
          label="Diagnosis"
          maxLength={2000}
          value={values.diagnosis}
          error={errors.diagnosis}
          onChange={(e) => set('diagnosis')(e.target.value)}
        />
      </div>
      <TextField
        id="estimated_cost"
        label="Estimated cost (₡ CRC)"
        inputMode="decimal"
        placeholder="e.g. 45000.00"
        value={values.estimated_cost}
        error={errors.estimated_cost}
        hint="Between ₡0 and ₡10,000,000."
        onChange={(e) => set('estimated_cost')(e.target.value)}
      />
    </div>
  );
}
