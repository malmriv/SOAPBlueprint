import re

# NCName: XML non-colonized name.
# Must start with letter or underscore, followed by letters, digits,
# hyphens, underscores, or periods. No spaces, no colons.
_NCNAME_RE = re.compile(r"^[a-zA-Z_][\w.\-]*$")

ALLOWED_TYPES = frozenset({
    "string",
    "int",
    "integer",
    "long",
    "short",
    "decimal",
    "float",
    "double",
    "boolean",
    "date",
    "dateTime",
    "time",
    "base64Binary",
    "hexBinary",
})


class ValidationError(Exception):
    pass


def validate_field_name(name: str) -> None:
    if not name:
        raise ValidationError("Field name cannot be empty.")
    if not _NCNAME_RE.match(name):
        raise ValidationError(
            f"Invalid XML name: {name!r}. "
            "Must start with a letter or underscore and contain only "
            "letters, digits, hyphens, underscores, or periods."
        )


def validate_field(field) -> None:
    """Validate a Field and all its descendants recursively."""
    validate_field_name(field.name)

    if field.is_complex:
        if not field.children:
            raise ValidationError(
                f"Complex field {field.name!r} has no children."
            )
        for child in field.children:
            validate_field(child)
    else:
        if field.type not in ALLOWED_TYPES:
            raise ValidationError(
                f"Field {field.name!r} has unknown type {field.type!r}. "
                f"Allowed types: {', '.join(sorted(ALLOWED_TYPES))}"
            )

    if isinstance(field.max_occurs, str) and field.max_occurs != "unbounded":
        raise ValidationError(
            f"Field {field.name!r}: max_occurs must be an int or 'unbounded', "
            f"got {field.max_occurs!r}."
        )
    if isinstance(field.max_occurs, int) and field.max_occurs < 1:
        raise ValidationError(
            f"Field {field.name!r}: max_occurs must be >= 1, got {field.max_occurs}."
        )
    if field.min_occurs < 0:
        raise ValidationError(
            f"Field {field.name!r}: min_occurs must be >= 0, got {field.min_occurs}."
        )


def validate_service_name(name: str) -> None:
    if not name:
        raise ValidationError("Service name cannot be empty.")
    if not _NCNAME_RE.match(name):
        raise ValidationError(f"Invalid service name: {name!r}.")
