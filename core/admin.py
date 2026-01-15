from django.contrib import admin
from django.utils.safestring import mark_safe 
from .models import (
    CustomUser, PlatformSettings, Level, BankDetails, Deposit, 
    Withdrawal, Task, Roulette, RouletteSettings, UserLevel, PlatformBankDetails
)

# --- CONFIGURAÇÕES DO USUÁRIO ---

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'available_balance', 'subsidy_balance', 'is_staff', 'is_active', 'date_joined', 'roulette_spins')
    search_fields = ('phone_number', 'invite_code')
    list_filter = ('is_staff', 'is_active', 'level_active')
    ordering = ('-date_joined',)

# --- CONFIGURAÇÕES DE DEPÓSITO ---

@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'payment_method', 'payer_name', 'is_approved', 'created_at', 'proof_link') 
    search_fields = ('user__phone_number', 'payer_name')
    list_filter = ('is_approved', 'payment_method', 'created_at')
    
    readonly_fields = ('current_proof_display', 'created_at')
    fieldsets = (
        ('Informações do Usuário', {
            'fields': ('user', 'amount', 'payment_method', 'payer_name')
        }),
        ('Status e Aprovação', {
            'fields': ('is_approved', 'created_at')
        }),
        ('Visualização do Comprovativo', {
            'fields': ('current_proof_display',),
        }),
    )

    def proof_link(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'<a href="{obj.proof_of_payment.url}" target="_blank" style="color: #2e7d32; font-weight: bold;">Ver Imagem</a>')
        return "Nenhum"
    proof_link.short_description = 'Comprovativo'

    def current_proof_display(self, obj):
        if obj.proof_of_payment:
            return mark_safe(f'''
                <div style="margin-bottom: 10px;">
                    <a href="{obj.proof_of_payment.url}" target="_blank" class="button" style="background: #0056b3; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px;">Abrir em ecrã inteiro</a>
                </div>
                <img src="{obj.proof_of_payment.url}" style="max-width: 450px; height: auto; border: 2px solid #ddd; border-radius: 8px;" />
            ''')
        return "Nenhum Comprovativo Carregado"
    current_proof_display.short_description = 'Foto do Comprovativo'

# --- CONFIGURAÇÕES DE SAQUE (ATUALIZADO COM MÉTODO E DETALHES) ---

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    # Mostra o método e detalhes na lista principal
    list_display = ('user', 'amount', 'method', 'status', 'created_at')
    search_fields = ('user__phone_number', 'withdrawal_details')
    list_filter = ('status', 'method', 'created_at')
    list_editable = ('status',)
    
    # Organiza os campos para facilitar o pagamento por parte do admin
    fieldsets = (
        ('Informações de Solicitação', {
            'fields': ('user', 'amount', 'status')
        }),
        ('Dados para Pagamento', {
            'fields': ('method', 'withdrawal_details'),
            'description': 'Estes são os dados fornecidos pelo cliente para o recebimento.'
        }),
        ('Datas', {
            'fields': ('created_at',),
        }),
    )
    readonly_fields = ('created_at',)

# --- NÍVEIS E PLATAFORMA ---

@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'whatsapp_link', 'history_text', 'deposit_instruction', 'withdrawal_instruction')

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'deposit_value', 'daily_gain', 'monthly_gain', 'cycle_days')
    search_fields = ('name',)

@admin.register(PlatformBankDetails)
class PlatformBankDetailsAdmin(admin.ModelAdmin):
    list_display = ('bank_name', 'account_holder_name', 'IBAN')
    search_fields = ('bank_name', 'account_holder_name')

# --- TAREFAS E HISTÓRICO ---

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'earnings', 'completed_at')
    search_fields = ('user__phone_number',)
    list_filter = ('completed_at',)

@admin.register(UserLevel)
class UserLevelAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'purchase_date', 'is_active')
    search_fields = ('user__phone_number', 'level__name')
    list_filter = ('is_active', 'level')

# --- ROLETA ---

@admin.register(Roulette)
class RouletteAdmin(admin.ModelAdmin):
    list_display = ('user', 'prize', 'is_approved', 'spin_date')
    list_filter = ('is_approved',)

@admin.register(RouletteSettings)
class RouletteSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'prizes')

@admin.register(BankDetails)
class BankDetailsAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_holder_name')
    search_fields = ('user__phone_number', 'bank_name')
    