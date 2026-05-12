"use client";

import { DataSourceId } from "@/lib/sources";
import { CollectionParams } from "@/lib/types";
import ResultsLimitInput from "@/components/ResultsLimitInput";
import HandlesInput from "@/components/HandlesInput";

interface ParametersInputProps {
  source: DataSourceId;
  value: CollectionParams;
  onChange: (value: CollectionParams) => void;
  onLimitFocus?: () => void;
}

export default function ParametersInput({
  source: _source,
  value,
  onChange,
  onLimitFocus,
}: ParametersInputProps) {
  return (
    <div className="flex flex-col gap-4">
      <ResultsLimitInput
        value={value.limit}
        onChange={(limit) => onChange({ ...value, limit })}
        onFocus={onLimitFocus}
      />
      <HandlesInput
        value={value.handles ?? []}
        onChange={(handles) => onChange({ ...value, handles })}
      />
    </div>
  );
}
