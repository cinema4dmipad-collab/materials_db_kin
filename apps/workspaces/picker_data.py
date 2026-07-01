def workspace_users_for_picker(users):
    rows = []
    for user in users:
        rows.append(
            {
                'user_id': user.pk,
                'username': user.username,
                'full_name': user.get_full_name().strip(),
                'email': user.email or '',
            }
        )
    return rows
