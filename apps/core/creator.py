def creator_label(user) -> str:
    if user is None:
        return ''
    full_name = user.get_full_name().strip()
    return full_name or user.get_username()


def assign_creator(instance, user) -> None:
    if user is None or not getattr(user, 'is_authenticated', False):
        return
    label = creator_label(user)
    if hasattr(instance, 'created_by_user_id') or hasattr(instance, 'created_by_user'):
        instance.created_by_user = user
    if hasattr(instance, 'created_by'):
        instance.created_by = label
    if hasattr(instance, 'uploaded_by_user_id') or hasattr(instance, 'uploaded_by_user'):
        instance.uploaded_by_user = user
    if hasattr(instance, 'uploaded_by'):
        instance.uploaded_by = label


def get_creator_display(obj) -> str:
    if obj is None:
        return '—'
    for user_field in ('created_by_user', 'uploaded_by_user'):
        user = getattr(obj, user_field, None)
        if user is not None:
            label = creator_label(user)
            if label:
                return label
    for label_field in ('created_by', 'uploaded_by'):
        label = (getattr(obj, label_field, '') or '').strip()
        if label:
            return label
    return '—'
