from ..units.conversion import dimension_of, is_known_unit
from ..units.tables import ALLOWED_DATA_TYPES, NUMERIC_TYPES
from .exceptions import ValidationError
from .mapping import PointMapping

MIN_PROTOCOLS = 2


def validate_mapping(mapping: PointMapping) -> None:
    _validate_minimum_protocol_count(mapping)
    _validate_binding_protocol_consistency(mapping)
    _validate_addresses(mapping)
    _validate_data_types_allowed(mapping)
    _validate_data_type_compatibility(mapping)
    _validate_scales(mapping)
    _validate_units_known(mapping)
    _validate_dimension_compatibility(mapping)
    _validate_engineering_ranges(mapping)
    _validate_protocol_metadata(mapping)


def _validate_minimum_protocol_count(mapping: PointMapping) -> None:
    if len(mapping.bindings) < MIN_PROTOCOLS:
        raise ValidationError(
            f"{mapping.point_id}: um mapeamento precisa de ao menos {MIN_PROTOCOLS} protocolos para fazer sentido em um gateway"
        )


def _validate_binding_protocol_consistency(mapping: PointMapping) -> None:
    for key, binding in mapping.bindings.items():
        if binding.protocol != key:
            raise ValidationError(
                f"{mapping.point_id}/{key}: campo 'protocol' do binding ('{binding.protocol}') não corresponde à chave declarada"
            )


def _validate_addresses(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        if not binding.address or not binding.address.strip():
            raise ValidationError(f"{mapping.point_id}/{proto}: endereço vazio")


def _validate_data_types_allowed(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        if binding.data_type not in ALLOWED_DATA_TYPES:
            raise ValidationError(
                f"{mapping.point_id}/{proto}: tipo de dado desconhecido '{binding.data_type}'"
            )


def _validate_data_type_compatibility(mapping: PointMapping) -> None:
    dtypes = {binding.data_type for binding in mapping.bindings.values()}
    if len(dtypes) > 1 and not dtypes.issubset(NUMERIC_TYPES):
        raise ValidationError(
            f"{mapping.point_id}: tipos de dado incompatíveis entre protocolos: {sorted(dtypes)}"
        )


def _validate_scales(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        if binding.scale == 0:
            raise ValidationError(f"{mapping.point_id}/{proto}: escala não pode ser zero")


def _validate_units_known(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        if not is_known_unit(binding.unit):
            raise ValidationError(
                f"{mapping.point_id}/{proto}: unidade desconhecida '{binding.unit}'"
            )


def _validate_dimension_compatibility(mapping: PointMapping) -> None:
    dims = {dimension_of(binding.unit) for binding in mapping.bindings.values()}
    if len(dims) > 1:
        raise ValidationError(
            f"{mapping.point_id}: dimensões físicas incompatíveis entre protocolos: {sorted(dims)}"
        )


def _validate_engineering_ranges(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        if binding.min_engineering is None or binding.max_engineering is None:
            continue
        if binding.min_engineering > binding.max_engineering:
            raise ValidationError(
                f"{mapping.point_id}/{proto}: faixa inválida (mínimo maior que máximo)"
            )


def _validate_protocol_metadata(mapping: PointMapping) -> None:
    for proto, binding in mapping.bindings.items():
        metadata = binding.protocol_metadata
        if proto == "dnp3":
            required = {"group", "variation", "index"}
            missing = sorted(required - metadata.keys())
            if missing:
                raise ValidationError(
                    f"{mapping.point_id}/dnp3: metadados obrigatórios ausentes: {missing}"
                )
            if not isinstance(metadata["group"], int) or not isinstance(metadata["variation"], int) or not isinstance(metadata["index"], int):
                raise ValidationError(f"{mapping.point_id}/dnp3: group, variation e index devem ser inteiros")
        if proto == "modbus":
            if "function_code" not in metadata or "register" not in metadata:
                raise ValidationError(f"{mapping.point_id}/modbus: function_code e register são obrigatórios")
        if proto == "opcua":
            if "namespace" not in metadata or "identifier_type" not in metadata:
                raise ValidationError(f"{mapping.point_id}/opcua: namespace e identifier_type são obrigatórios")
        if proto == "mms":
            if "functional_constraint" not in metadata:
                raise ValidationError(f"{mapping.point_id}/mms: functional_constraint é obrigatório")
