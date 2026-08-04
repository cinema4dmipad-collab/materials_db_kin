from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from dmr.security.token.app.models import Token

from apps.api.token_forms import ApiTokenCreateForm, ApiTokenUpdateForm


def _user_tokens(user):
    return Token.objects.filter(user=user).order_by('-created_at')


class TokenCreateView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        form = ApiTokenCreateForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Не удалось создать токен. Проверьте форму.')
            return redirect('accounts:profile')

        token, raw = Token.issue(
            user=request.user,
            name=form.cleaned_data['name'].strip(),
            expires_at=form.cleaned_expires_at(),
        )
        request.session['api_token_plaintext'] = raw
        request.session['api_token_name'] = token.name
        request.session['api_token_id'] = token.pk
        messages.success(
            request,
            'Токен создан. Скопируйте секрет сейчас — повторно показать его нельзя.',
        )
        return redirect('accounts:profile')


class TokenUpdateView(LoginRequiredMixin, View):
    http_method_names = ['get', 'post']

    def get(self, request, pk, *args, **kwargs):
        token = get_object_or_404(Token, pk=pk, user=request.user)
        form = ApiTokenUpdateForm(instance=token)
        return render(
            request,
            'accounts/token_edit.html',
            {'form': form, 'token': token},
        )

    def post(self, request, pk, *args, **kwargs):
        token = get_object_or_404(Token, pk=pk, user=request.user)
        form = ApiTokenUpdateForm(request.POST, instance=token)
        if not form.is_valid():
            return render(
                request,
                'accounts/token_edit.html',
                {'form': form, 'token': token},
            )
        token.name = form.cleaned_data['name'].strip()
        token.expires_at = form.cleaned_expires_at_value()
        token.save(update_fields=['name', 'expires_at', 'updated_at'])
        messages.success(request, 'Токен обновлён.')
        return redirect('accounts:profile')


class TokenRotateView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk, *args, **kwargs):
        token = get_object_or_404(Token, pk=pk, user=request.user)
        name = token.name
        expires_at = token.expires_at
        token.revoke()
        new_token, raw = Token.issue(
            user=request.user,
            name=name,
            expires_at=expires_at,
        )
        request.session['api_token_plaintext'] = raw
        request.session['api_token_name'] = name
        request.session['api_token_id'] = new_token.pk
        messages.success(
            request,
            'Секрет обновлён. Скопируйте его сейчас — повторно показать нельзя.',
        )
        return redirect('accounts:profile')


class TokenRevokeView(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk, *args, **kwargs):
        token = get_object_or_404(Token, pk=pk, user=request.user)
        if token.revoked_at is None:
            token.revoke()
            messages.success(request, f'Токен «{token.name}» отозван.')
        else:
            messages.info(request, 'Токен уже был отозван.')
        if request.session.get('api_token_id') == token.pk:
            request.session.pop('api_token_plaintext', None)
            request.session.pop('api_token_name', None)
            request.session.pop('api_token_id', None)
        return redirect('accounts:profile')


class TokenSecretDismissView(LoginRequiredMixin, View):
    """Сбрасывает одноразовый секрет из сессии после закрытия модалки."""

    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        request.session.pop('api_token_plaintext', None)
        request.session.pop('api_token_name', None)
        request.session.pop('api_token_id', None)
        return redirect('accounts:profile')
